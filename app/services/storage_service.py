"""S3 Storage Service for file uploads.

Handles uploading and managing files in S3/MinIO including:
- Listing photos
- User profile photos
- Identity documents
- Message attachments
"""

import mimetypes
import uuid
from datetime import timedelta
from io import BytesIO
from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from PIL import Image

from app.config import settings


class StorageService:
    """S3/MinIO storage service for file uploads."""

    # Allowed image types
    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_DOCUMENT_SIZE = 20 * 1024 * 1024  # 20MB

    # Image sizes for resizing
    IMAGE_SIZES = {
        "thumbnail": (200, 200),
        "medium": (800, 600),
        "large": (1600, 1200),
        "original": None,
    }

    def __init__(self) -> None:
        """Initialize S3 client."""
        self._client = None
        self._bucket = settings.s3_bucket_name

    @property
    def client(self):
        """Lazy-load S3 client."""
        if self._client is None:
            config = Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"},
            )
            self._client = boto3.client(
                "s3",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
                endpoint_url=settings.s3_endpoint_url,  # For MinIO in dev
                config=config,
            )
        return self._client

    def _generate_key(self, folder: str, filename: str) -> str:
        """Generate unique S3 key for a file.

        Args:
            folder: Folder path (e.g., 'listings/photos')
            filename: Original filename

        Returns:
            str: S3 key like 'listings/photos/uuid-filename.jpg'
        """
        # Get file extension
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
        unique_id = uuid.uuid4().hex[:12]
        return f"{folder}/{unique_id}.{ext}"

    def _get_content_type(self, filename: str) -> str:
        """Get content type from filename."""
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or "application/octet-stream"

    async def upload_file(
        self,
        file: BinaryIO,
        folder: str,
        filename: str,
        content_type: str | None = None,
        public: bool = True,
    ) -> str:
        """Upload a file to S3.

        Args:
            file: File-like object to upload
            folder: Destination folder
            filename: Original filename
            content_type: MIME type (auto-detected if not provided)
            public: Whether the file should be publicly accessible

        Returns:
            str: Public URL of the uploaded file
        """
        key = self._generate_key(folder, filename)
        content_type = content_type or self._get_content_type(filename)

        extra_args = {"ContentType": content_type}
        if public:
            extra_args["ACL"] = "public-read"

        self.client.upload_fileobj(file, self._bucket, key, ExtraArgs=extra_args)

        # Return public URL
        if settings.s3_endpoint_url:
            # MinIO in development
            return f"{settings.s3_endpoint_url}/{self._bucket}/{key}"
        else:
            # AWS S3
            return f"https://{self._bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"

    async def upload_image(
        self,
        file: BinaryIO,
        folder: str,
        filename: str,
        resize: bool = True,
    ) -> dict[str, str]:
        """Upload an image with optional resizing.

        Args:
            file: Image file to upload
            folder: Destination folder
            filename: Original filename
            resize: Whether to create multiple sizes

        Returns:
            dict: URLs for each size {'thumbnail': url, 'medium': url, ...}
        """
        # Read image
        image_data = file.read()
        if len(image_data) > self.MAX_IMAGE_SIZE:
            raise ValueError(f"Image exceeds maximum size of {self.MAX_IMAGE_SIZE // 1024 // 1024}MB")

        # Open with Pillow
        image = Image.open(BytesIO(image_data))

        # Convert RGBA to RGB for JPEG
        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background

        urls = {}
        base_key = self._generate_key(folder, filename).rsplit(".", 1)[0]

        for size_name, dimensions in self.IMAGE_SIZES.items():
            if not resize and size_name != "original":
                continue

            if dimensions:
                # Resize maintaining aspect ratio
                resized = image.copy()
                resized.thumbnail(dimensions, Image.Resampling.LANCZOS)
            else:
                resized = image

            # Save to buffer
            buffer = BytesIO()
            resized.save(buffer, format="JPEG", quality=85, optimize=True)
            buffer.seek(0)

            # Upload
            key = f"{base_key}_{size_name}.jpg"
            self.client.upload_fileobj(
                buffer,
                self._bucket,
                key,
                ExtraArgs={"ContentType": "image/jpeg", "ACL": "public-read"},
            )

            # Generate URL
            if settings.s3_endpoint_url:
                urls[size_name] = f"{settings.s3_endpoint_url}/{self._bucket}/{key}"
            else:
                urls[size_name] = f"https://{self._bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"

        return urls

    async def upload_listing_photo(self, file: BinaryIO, listing_id: str, filename: str) -> dict[str, str]:
        """Upload a listing photo with all sizes.

        Args:
            file: Image file
            listing_id: Listing UUID
            filename: Original filename

        Returns:
            dict: URLs for each size
        """
        folder = f"listings/{listing_id}/photos"
        return await self.upload_image(file, folder, filename, resize=True)

    async def upload_profile_photo(self, file: BinaryIO, user_id: str, filename: str) -> dict[str, str]:
        """Upload a user profile photo.

        Args:
            file: Image file
            user_id: User UUID
            filename: Original filename

        Returns:
            dict: URLs for each size
        """
        folder = f"users/{user_id}/profile"
        return await self.upload_image(file, folder, filename, resize=True)

    async def upload_identity_document(
        self,
        file: BinaryIO,
        user_id: str,
        doc_type: str,
        filename: str,
    ) -> str:
        """Upload an identity document (private).

        Args:
            file: Document file (image or PDF)
            user_id: User UUID
            doc_type: Document type (front, back, face)
            filename: Original filename

        Returns:
            str: S3 key (not public URL, requires signed URL to access)
        """
        # Identity documents are NOT public
        key = self._generate_key(f"identity/{user_id}/{doc_type}", filename)
        content_type = self._get_content_type(filename)

        file_data = file.read()
        if len(file_data) > self.MAX_DOCUMENT_SIZE:
            raise ValueError(f"Document exceeds maximum size of {self.MAX_DOCUMENT_SIZE // 1024 // 1024}MB")

        self.client.upload_fileobj(
            BytesIO(file_data),
            self._bucket,
            key,
            ExtraArgs={"ContentType": content_type},  # No ACL = private
        )

        return key

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for private files.

        Args:
            key: S3 object key
            expires_in: URL expiration in seconds

        Returns:
            str: Presigned URL
        """
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    async def delete_file(self, url_or_key: str) -> bool:
        """Delete a file from S3.

        Args:
            url_or_key: Full URL or S3 key

        Returns:
            bool: True if deleted successfully
        """
        # Extract key from URL if needed
        if url_or_key.startswith("http"):
            # Parse URL to get key
            key = url_or_key.split(f"{self._bucket}/")[-1]
        else:
            key = url_or_key

        try:
            self.client.delete_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    async def delete_listing_photos(self, listing_id: str) -> int:
        """Delete all photos for a listing.

        Args:
            listing_id: Listing UUID

        Returns:
            int: Number of files deleted
        """
        prefix = f"listings/{listing_id}/photos/"
        return await self._delete_prefix(prefix)

    async def _delete_prefix(self, prefix: str) -> int:
        """Delete all objects with a given prefix.

        Args:
            prefix: S3 key prefix

        Returns:
            int: Number of objects deleted
        """
        try:
            response = self.client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
            objects = response.get("Contents", [])

            if not objects:
                return 0

            delete_keys = [{"Key": obj["Key"]} for obj in objects]
            self.client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": delete_keys},
            )
            return len(delete_keys)
        except ClientError:
            return 0


# Singleton instance
storage_service = StorageService()
