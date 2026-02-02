"""Seed amenities data.

Revision ID: 002_seed_amenities
Revises: 001_initial
Create Date: 2024-01-19

Seeds the amenities table with standard property amenities
organized by category.
"""

import uuid
from typing import Sequence

from alembic import op
from sqlalchemy import insert, table, column, String
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision: str = "002_seed_amenities"
down_revision: str = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Amenities data organized by category
AMENITIES = [
    # ===== ESSENTIALS =====
    {"name": "WiFi", "category": "Essentials", "icon": "wifi"},
    {"name": "Air conditioning", "category": "Essentials", "icon": "air"},
    {"name": "Heating", "category": "Essentials", "icon": "thermostat"},
    {"name": "Washer", "category": "Essentials", "icon": "local_laundry_service"},
    {"name": "Dryer", "category": "Essentials", "icon": "dry"},
    {"name": "TV", "category": "Essentials", "icon": "tv"},
    {"name": "Iron", "category": "Essentials", "icon": "iron"},
    {"name": "Hair dryer", "category": "Essentials", "icon": "dry"},
    {"name": "Hot water", "category": "Essentials", "icon": "hot_tub"},
    {"name": "Bed linens", "category": "Essentials", "icon": "bed"},
    {"name": "Towels", "category": "Essentials", "icon": "dry_cleaning"},
    {"name": "Hangers", "category": "Essentials", "icon": "checkroom"},

    # ===== KITCHEN =====
    {"name": "Kitchen", "category": "Kitchen", "icon": "kitchen"},
    {"name": "Refrigerator", "category": "Kitchen", "icon": "kitchen"},
    {"name": "Microwave", "category": "Kitchen", "icon": "microwave"},
    {"name": "Stove", "category": "Kitchen", "icon": "local_fire_department"},
    {"name": "Oven", "category": "Kitchen", "icon": "local_fire_department"},
    {"name": "Cooking basics", "category": "Kitchen", "icon": "soup_kitchen"},
    {"name": "Dishes and silverware", "category": "Kitchen", "icon": "restaurant"},
    {"name": "Coffee maker", "category": "Kitchen", "icon": "coffee_maker"},
    {"name": "Tea kettle", "category": "Kitchen", "icon": "coffee"},
    {"name": "Dishwasher", "category": "Kitchen", "icon": "dish"},
    {"name": "Toaster", "category": "Kitchen", "icon": "breakfast_dining"},
    {"name": "Blender", "category": "Kitchen", "icon": "blender"},
    {"name": "Dining table", "category": "Kitchen", "icon": "table_restaurant"},

    # ===== BATHROOM =====
    {"name": "Bathtub", "category": "Bathroom", "icon": "bathtub"},
    {"name": "Shower", "category": "Bathroom", "icon": "shower"},
    {"name": "Toiletries", "category": "Bathroom", "icon": "soap"},
    {"name": "Bidet", "category": "Bathroom", "icon": "water_drop"},
    {"name": "Cleaning products", "category": "Bathroom", "icon": "cleaning_services"},

    # ===== BEDROOM =====
    {"name": "King bed", "category": "Bedroom", "icon": "king_bed"},
    {"name": "Queen bed", "category": "Bedroom", "icon": "bed"},
    {"name": "Single bed", "category": "Bedroom", "icon": "single_bed"},
    {"name": "Sofa bed", "category": "Bedroom", "icon": "weekend"},
    {"name": "Air mattress", "category": "Bedroom", "icon": "air"},
    {"name": "Blackout curtains", "category": "Bedroom", "icon": "curtains"},
    {"name": "Wardrobe", "category": "Bedroom", "icon": "door_sliding"},
    {"name": "Extra pillows and blankets", "category": "Bedroom", "icon": "bed"},
    {"name": "Room-darkening shades", "category": "Bedroom", "icon": "blinds"},

    # ===== OUTDOOR =====
    {"name": "Garden", "category": "Outdoor", "icon": "yard"},
    {"name": "Balcony", "category": "Outdoor", "icon": "balcony"},
    {"name": "Patio", "category": "Outdoor", "icon": "deck"},
    {"name": "Terrace", "category": "Outdoor", "icon": "deck"},
    {"name": "BBQ grill", "category": "Outdoor", "icon": "outdoor_grill"},
    {"name": "Outdoor furniture", "category": "Outdoor", "icon": "chair"},
    {"name": "Outdoor dining area", "category": "Outdoor", "icon": "table_restaurant"},
    {"name": "Sun loungers", "category": "Outdoor", "icon": "beach_access"},

    # ===== PARKING =====
    {"name": "Free parking on premises", "category": "Parking", "icon": "local_parking"},
    {"name": "Free street parking", "category": "Parking", "icon": "local_parking"},
    {"name": "Paid parking on premises", "category": "Parking", "icon": "local_parking"},
    {"name": "Paid parking off premises", "category": "Parking", "icon": "local_parking"},
    {"name": "Garage", "category": "Parking", "icon": "garage"},
    {"name": "EV charger", "category": "Parking", "icon": "ev_station"},

    # ===== SAFETY =====
    {"name": "Smoke alarm", "category": "Safety", "icon": "detector_smoke"},
    {"name": "Carbon monoxide alarm", "category": "Safety", "icon": "detector_smoke"},
    {"name": "Fire extinguisher", "category": "Safety", "icon": "fire_extinguisher"},
    {"name": "First aid kit", "category": "Safety", "icon": "medical_services"},
    {"name": "Security cameras", "category": "Safety", "icon": "videocam"},
    {"name": "Lock on bedroom door", "category": "Safety", "icon": "lock"},
    {"name": "Safe", "category": "Safety", "icon": "security"},

    # ===== FACILITIES =====
    {"name": "Pool", "category": "Facilities", "icon": "pool"},
    {"name": "Hot tub", "category": "Facilities", "icon": "hot_tub"},
    {"name": "Gym", "category": "Facilities", "icon": "fitness_center"},
    {"name": "Sauna", "category": "Facilities", "icon": "spa"},
    {"name": "Elevator", "category": "Facilities", "icon": "elevator"},
    {"name": "Doorman", "category": "Facilities", "icon": "person"},

    # ===== ENTERTAINMENT =====
    {"name": "Smart TV", "category": "Entertainment", "icon": "connected_tv"},
    {"name": "Cable TV", "category": "Entertainment", "icon": "tv"},
    {"name": "Netflix", "category": "Entertainment", "icon": "play_circle"},
    {"name": "Amazon Prime Video", "category": "Entertainment", "icon": "play_circle"},
    {"name": "Sound system", "category": "Entertainment", "icon": "speaker"},
    {"name": "Books and reading material", "category": "Entertainment", "icon": "book"},
    {"name": "Board games", "category": "Entertainment", "icon": "casino"},
    {"name": "Gaming console", "category": "Entertainment", "icon": "videogame_asset"},

    # ===== WORK =====
    {"name": "Dedicated workspace", "category": "Work", "icon": "desk"},
    {"name": "Laptop-friendly workspace", "category": "Work", "icon": "laptop_mac"},
    {"name": "Printer", "category": "Work", "icon": "print"},
    {"name": "High-speed internet", "category": "Work", "icon": "wifi"},

    # ===== FAMILY =====
    {"name": "Baby cot", "category": "Family", "icon": "child_care"},
    {"name": "High chair", "category": "Family", "icon": "chair"},
    {"name": "Baby bath", "category": "Family", "icon": "bathtub"},
    {"name": "Baby monitor", "category": "Family", "icon": "monitor"},
    {"name": "Children's books and toys", "category": "Family", "icon": "toys"},
    {"name": "Baby safety gates", "category": "Family", "icon": "security"},

    # ===== ACCESSIBILITY =====
    {"name": "Step-free access", "category": "Accessibility", "icon": "accessible"},
    {"name": "Wide doorway", "category": "Accessibility", "icon": "door_front"},
    {"name": "Wide hallway clearance", "category": "Accessibility", "icon": "meeting_room"},
    {"name": "Accessible-height bed", "category": "Accessibility", "icon": "bed"},
    {"name": "Accessible-height toilet", "category": "Accessibility", "icon": "wc"},
    {"name": "Roll-in shower", "category": "Accessibility", "icon": "shower"},
    {"name": "Grab bars", "category": "Accessibility", "icon": "accessibility"},
    {"name": "Shower chair", "category": "Accessibility", "icon": "accessible"},

    # ===== LOCATION FEATURES =====
    {"name": "Mountain view", "category": "Location", "icon": "terrain"},
    {"name": "City view", "category": "Location", "icon": "location_city"},
    {"name": "Garden view", "category": "Location", "icon": "park"},
    {"name": "Waterfront", "category": "Location", "icon": "water"},
    {"name": "Lake access", "category": "Location", "icon": "water"},
    {"name": "Beach access", "category": "Location", "icon": "beach_access"},
    {"name": "Ski-in/Ski-out", "category": "Location", "icon": "downhill_skiing"},

    # ===== PETS =====
    {"name": "Pets allowed", "category": "Pets", "icon": "pets"},
    {"name": "Cat friendly", "category": "Pets", "icon": "pets"},
    {"name": "Dog friendly", "category": "Pets", "icon": "pets"},
    {"name": "Pet bowls", "category": "Pets", "icon": "pets"},

    # ===== SERVICES =====
    {"name": "Self check-in", "category": "Services", "icon": "key"},
    {"name": "Keypad", "category": "Services", "icon": "dialpad"},
    {"name": "Smart lock", "category": "Services", "icon": "lock"},
    {"name": "Lockbox", "category": "Services", "icon": "lock"},
    {"name": "Cleaning service available", "category": "Services", "icon": "cleaning_services"},
    {"name": "Breakfast included", "category": "Services", "icon": "breakfast_dining"},
    {"name": "Airport shuttle", "category": "Services", "icon": "airport_shuttle"},
    {"name": "Host greets you", "category": "Services", "icon": "waving_hand"},
    {"name": "Long term stays allowed", "category": "Services", "icon": "calendar_month"},
    {"name": "Luggage storage", "category": "Services", "icon": "luggage"},
]


def upgrade() -> None:
    """Insert seed amenities."""
    amenities_table = table(
        "amenities",
        column("id", UUID(as_uuid=True)),
        column("name", String),
        column("category", String),
        column("icon", String),
    )

    # Generate UUIDs for each amenity
    amenities_with_ids = [
        {
            "id": str(uuid.uuid4()),
            "name": a["name"],
            "category": a["category"],
            "icon": a["icon"],
        }
        for a in AMENITIES
    ]

    op.bulk_insert(amenities_table, amenities_with_ids)


def downgrade() -> None:
    """Remove seed amenities."""
    # Delete all seeded amenities
    amenity_names = [a["name"] for a in AMENITIES]
    amenities_table = table("amenities", column("name", String))

    op.execute(
        amenities_table.delete().where(amenities_table.c.name.in_(amenity_names))
    )
