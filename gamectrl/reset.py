#!/usr/bin/env python3
"""
CTF Gameserver Reset Tool
Provides full and basic reset functionality for CTF competitions
"""

import psycopg2
import sys
import os
from datetime import datetime, timezone
import argparse
import getpass

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "database": "ctf_gameserver",
    "user": "ctf_web",
    "password": None,  # Will be prompted
}

# Default values for game configuration
DEFAULT_CONFIG = {
    "competition_name": "Academy CTF",
    "services_public": None,  # Will be set to None (NULL in database)
    "start": None,  # Will be set to None (NULL in database)
    "end": None,  # Will be set to None (NULL in database)
    "tick_duration": 60,
    "valid_ticks": 5,
    "current_tick": 0,
    "cancel_checks": False,
    "flag_prefix": "FLAG_",
    "registration_open": True,
    "registration_confirm_text": "",
    "min_net_number": 1,
    "max_net_number": None,  # Will be set to None (NULL in database)
}

# Admin user configuration
ADMIN_CONFIG = {
    "username": "admin",
    "email": "ctf@x3ero0.dev",
    "password": None,  # Will be prompted during full reset
}

# Default team download entries
DEFAULT_TEAMDOWNLOADS = [
    {
        "filename": "wg-ctf.conf",
        "description": "Wireguard vpn configuration for the vulnbox.",
    },
    {
        "filename": "player.ovpn",
        "description": "Openvpn configuration for players to use.",
    },
]

# Default flatpage categories
DEFAULT_FLATPAGE_CATEGORIES = [
    {"title": "Information", "slug": "information", "ordering": 1}
]

# Default flatpages (markdown files to load from disk)
DEFAULT_FLATPAGES = [
    {
        "file_path": "../markdowns/attack-defense-for-beginners.md",
        "title": "Attack Defense for Beginners",
        "slug": "attack-defense-for-beginners",
        "category": "Information",
        "ordering": 1,
    },
    {
        "file_path": "../markdowns/submission.md",
        "title": "Submission",
        "slug": "submission",
        "category": "Information",
        "ordering": 2,
    },
    {
        "file_path": "../markdowns/vulnbox-setup.md",
        "title": "Vulnbox Setup",
        "slug": "vulnbox-setup",
        "category": "Information",
        "ordering": 3,
    },
    {
        "file_path": "../markdowns/index.md",
        "title": "",
        "slug": "index",
        "category": "",  # No category (NULL)
        "ordering": 0,
    },
]


def connect_to_database():
    """Connect to the CTF database"""
    try:
        # Prompt for password if not provided
        if DB_CONFIG["password"] is None:
            DB_CONFIG["password"] = getpass.getpass(
                f"Password for {DB_CONFIG['user']}@{DB_CONFIG['host']}: "
            )

        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def basic_reset(conn):
    """
    Basic reset: Clear game data but keep teams, services, users, and sessions
    - Reset current_tick to 0
    - Clear all flags, captures, scoreboard, vpn status, service status
    - Keep teams, services, users, and sessions intact
    """
    print("Performing basic reset...")

    cursor = conn.cursor()

    try:
        # Clear game data tables in correct order (respecting foreign key constraints)
        print("- Clearing captures...")
        cursor.execute("DELETE FROM scoring_capture;")

        print("- Clearing scoreboard...")
        cursor.execute("DELETE FROM scoring_scoreboard;")

        print("- Clearing status checks...")
        cursor.execute("DELETE FROM scoring_statuscheck;")

        print("- Clearing checker states...")
        cursor.execute("DELETE FROM scoring_checkerstate;")

        print("- Clearing flags...")
        cursor.execute("DELETE FROM scoring_flag;")

        print("- Clearing VPN status...")
        cursor.execute("DELETE FROM vpnstatus_vpnstatuscheck;")

        # Reset current tick and clear start/end times to stop checker confusion
        print("- Resetting current tick and clearing game times...")
        cursor.execute("UPDATE scoring_gamecontrol SET current_tick = 0")

        print("✓ Basic reset completed successfully!")
        print("✓ Teams, users, sessions, and services preserved")

        # Show current state
        show_current_state(cursor)

    except psycopg2.Error as e:
        print(f"Error during basic reset: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        cursor.close()


def full_reset(conn):
    """
    Full reset: Reset everything to initial state
    - Reset all game control settings to defaults
    - Remove all teams except admin
    - Remove all services
    - Clear all game data
    """
    print("Performing full reset...")

    cursor = conn.cursor()

    try:
        # First do basic reset to clear game data (in correct order for foreign keys)
        print("- Clearing all game data...")
        cursor.execute("DELETE FROM scoring_capture;")
        cursor.execute("DELETE FROM scoring_scoreboard;")
        cursor.execute("DELETE FROM scoring_statuscheck;")
        cursor.execute("DELETE FROM scoring_checkerstate;")
        cursor.execute("DELETE FROM scoring_flag;")
        cursor.execute("DELETE FROM vpnstatus_vpnstatuscheck;")
        cursor.execute("DELETE FROM registration_teamdownload;")
        cursor.execute("DELETE FROM flatpages_flatpage;")
        cursor.execute("DELETE FROM flatpages_category;")
        cursor.execute("DELETE FROM django_admin_log;")
        cursor.execute("DELETE FROM django_session;")

        # Remove all services
        print("- Removing all services...")
        cursor.execute("DELETE FROM scoring_service;")

        # Remove all teams and users (including admin - will recreate)
        print("- Removing all teams and users...")
        cursor.execute("DELETE FROM auth_user_groups;")
        cursor.execute("DELETE FROM auth_user_user_permissions;")
        cursor.execute("DELETE FROM registration_team;")
        cursor.execute("DELETE FROM auth_user;")

        # Recreate admin user
        print("- Recreating admin user...")

        # Prompt for admin password if not provided
        admin_password = ADMIN_CONFIG["password"]
        if admin_password is None:
            admin_password = getpass.getpass(
                f"Set password for admin user '{ADMIN_CONFIG['username']}': "
            )

        # Create proper Django password hash
        import hashlib
        import base64
        import secrets

        # Generate salt and hash password (Django PBKDF2 format)
        salt = base64.b64encode(secrets.token_bytes(16)).decode("ascii")[:22]
        password_hash = hashlib.pbkdf2_hmac(
            "sha256", admin_password.encode(), salt.encode(), 600000
        )
        password_b64 = base64.b64encode(password_hash).decode("ascii")[:43]
        django_hash = f"pbkdf2_sha256$600000${salt}${password_b64}="

        # Insert admin user with correct password hash directly
        cursor.execute(
            """
            INSERT INTO auth_user (username, first_name, last_name, email, is_staff, is_active, is_superuser, date_joined, password)
            VALUES (%s, '', '', %s, true, true, true, NOW(), %s)
        """,
            (ADMIN_CONFIG["username"], ADMIN_CONFIG["email"], django_hash),
        )

        # Reset game control to default values
        print("- Resetting game control to defaults...")
        update_query = """
        UPDATE scoring_gamecontrol SET 
            competition_name = %s,
            services_public = %s,
            start = %s,
            "end" = %s,
            tick_duration = %s,
            valid_ticks = %s,
            current_tick = %s,
            cancel_checks = %s,
            flag_prefix = %s,
            registration_open = %s,
            registration_confirm_text = %s,
            min_net_number = %s,
            max_net_number = %s
        """

        cursor.execute(
            update_query,
            (
                DEFAULT_CONFIG["competition_name"],
                DEFAULT_CONFIG["services_public"],
                DEFAULT_CONFIG["start"],
                DEFAULT_CONFIG["end"],
                DEFAULT_CONFIG["tick_duration"],
                DEFAULT_CONFIG["valid_ticks"],
                DEFAULT_CONFIG["current_tick"],
                DEFAULT_CONFIG["cancel_checks"],
                DEFAULT_CONFIG["flag_prefix"],
                DEFAULT_CONFIG["registration_open"],
                DEFAULT_CONFIG["registration_confirm_text"],
                DEFAULT_CONFIG["min_net_number"],
                DEFAULT_CONFIG["max_net_number"],
            ),
        )

        # Recreate default team download entries
        print("- Creating default team download entries...")
        for download in DEFAULT_TEAMDOWNLOADS:
            cursor.execute(
                """
                INSERT INTO registration_teamdownload (filename, description)
                VALUES (%s, %s)
                """,
                (download["filename"], download["description"]),
            )
            print(f"  - Added: {download['filename']}")

        # Recreate default flatpage categories
        print("- Creating default flatpage categories...")
        category_ids = {}  # Store category_id mapping for flatpages

        for category in DEFAULT_FLATPAGE_CATEGORIES:
            cursor.execute(
                """
                INSERT INTO flatpages_category (title, slug, ordering)
                VALUES (%s, %s, %s) RETURNING id
                """,
                (category["title"], category["slug"], category["ordering"]),
            )
            category_id = cursor.fetchone()[0]
            category_ids[category["title"]] = category_id
            print(f"  - Added category: {category['title']} (ID: {category_id})")

        # Recreate default flatpages from markdown files
        print("- Creating default flatpages from markdown files...")
        for flatpage in DEFAULT_FLATPAGES:
            try:
                # Read markdown file content
                if os.path.exists(flatpage["file_path"]):
                    with open(flatpage["file_path"], "r", encoding="utf-8") as f:
                        content = f.read()

                    # Get category_id (None for empty category)
                    category_id = None
                    if flatpage["category"] and flatpage["category"] in category_ids:
                        category_id = category_ids[flatpage["category"]]

                    # Insert flatpage
                    cursor.execute(
                        """
                        INSERT INTO flatpages_flatpage (title, content, ordering, slug, category_id)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            flatpage["title"],
                            content,
                            flatpage["ordering"],
                            flatpage["slug"],
                            category_id,
                        ),
                    )
                    print(
                        f"  - Added flatpage: {flatpage['title']} ({flatpage['file_path']})"
                    )
                else:
                    print(f"  - WARNING: File not found: {flatpage['file_path']}")

            except Exception as e:
                print(f"  - ERROR loading {flatpage['file_path']}: {e}")

        print("✓ Full reset completed successfully!")

        # Show current state
        show_current_state(cursor)

    except psycopg2.Error as e:
        print(f"Error during full reset: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        cursor.close()


def show_current_state(cursor):
    """Display current database state after reset"""
    print("\n" + "=" * 50)
    print("CURRENT STATE AFTER RESET")
    print("=" * 50)

    # Game control
    cursor.execute("SELECT * FROM scoring_gamecontrol;")
    gamecontrol = cursor.fetchone()
    if gamecontrol:
        print(f"Competition: {gamecontrol[1]}")
        print(f"Current Tick: {gamecontrol[7]}")
        print(f"Registration Open: {gamecontrol[10]}")
        print(f"Start Time: {gamecontrol[3] or 'Not set'}")
        print(f"End Time: {gamecontrol[4] or 'Not set'}")

    # Count various entities
    cursor.execute("SELECT COUNT(*) FROM registration_team;")
    team_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM scoring_service;")
    service_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM scoring_flag;")
    flag_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM scoring_capture;")
    capture_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM auth_user WHERE is_superuser = false;")
    user_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM auth_user WHERE is_superuser = true;")
    admin_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM registration_teamdownload;")
    download_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM flatpages_category;")
    category_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM flatpages_flatpage;")
    flatpage_count = cursor.fetchone()[0]

    print(f"\nDatabase Counts:")
    print(f"- Teams: {team_count}")
    print(f"- Services: {service_count}")
    print(f"- Flags: {flag_count}")
    print(f"- Captures: {capture_count}")
    print(f"- Regular Users: {user_count}")
    print(f"- Admin Users: {admin_count}")
    print(f"- Team Downloads: {download_count}")
    print(f"- Flatpage Categories: {category_count}")
    print(f"- Flatpages: {flatpage_count}")

    # Show services if any
    if service_count > 0:
        cursor.execute("SELECT name, slug FROM scoring_service;")
        services = cursor.fetchall()
        print(f"\nServices:")
        for service in services:
            print(f"- {service[0]} ({service[1]})")

    # Show admin users
    cursor.execute("SELECT username, email FROM auth_user WHERE is_superuser = true;")
    admins = cursor.fetchall()
    print(f"\nAdmin Users:")
    for admin in admins:
        print(f"- {admin[0]} ({admin[1]})")

    # Show team downloads
    if download_count > 0:
        cursor.execute("SELECT filename, description FROM registration_teamdownload;")
        downloads = cursor.fetchall()
        print(f"\nTeam Downloads:")
        for download in downloads:
            print(f"- {download[0]}: {download[1]}")

    # Show flatpage categories
    if category_count > 0:
        cursor.execute(
            "SELECT id, title, slug FROM flatpages_category ORDER BY ordering;"
        )
        categories = cursor.fetchall()
        print(f"\nFlatpage Categories:")
        for category in categories:
            print(f"- {category[1]} ({category[2]}) [ID: {category[0]}]")

    # Show flatpages
    if flatpage_count > 0:
        cursor.execute(
            """
            SELECT f.title, f.slug, c.title as category_title 
            FROM flatpages_flatpage f 
            LEFT JOIN flatpages_category c ON f.category_id = c.id 
            ORDER BY f.ordering
        """
        )
        flatpages = cursor.fetchall()
        print(f"\nFlatpages:")
        for flatpage in flatpages:
            category = flatpage[2] if flatpage[2] else "No category"
            print(f"- {flatpage[0]} ({flatpage[1]}) [{category}]")


def update_defaults(key, value):
    """Update default configuration values"""
    if key in DEFAULT_CONFIG:
        # Convert string values to appropriate types
        if key in [
            "tick_duration",
            "valid_ticks",
            "current_tick",
            "min_net_number",
            "max_net_number",
        ]:
            try:
                DEFAULT_CONFIG[key] = int(value) if value != "None" else None
            except ValueError:
                print(f"Error: {key} must be an integer")
                return False
        elif key in ["cancel_checks", "registration_open"]:
            DEFAULT_CONFIG[key] = value.lower() in ["true", "1", "yes", "on"]
        else:
            DEFAULT_CONFIG[key] = value if value != "None" else None
        return True
    elif key in ADMIN_CONFIG:
        ADMIN_CONFIG[key] = value
        return True
    else:
        print(f"Error: Unknown configuration key '{key}'")
        print(
            f"Available keys: {', '.join(list(DEFAULT_CONFIG.keys()) + list(ADMIN_CONFIG.keys()))}"
        )
        return False


def main():
    parser = argparse.ArgumentParser(description="CTF Gameserver Reset Tool")
    parser.add_argument(
        "reset_type", choices=["basic", "full"], help="Type of reset to perform"
    )
    parser.add_argument(
        "--set",
        nargs=2,
        metavar=("KEY", "VALUE"),
        action="append",
        help="Set default configuration values (can be used multiple times)",
    )
    parser.add_argument(
        "--show-config", action="store_true", help="Show current default configuration"
    )

    args = parser.parse_args()

    # Update default configuration if requested
    if args.set:
        for key, value in args.set:
            if not update_defaults(key, value):
                sys.exit(1)

    # Show configuration if requested
    if args.show_config:
        print("Current Default Configuration:")
        print("-" * 30)
        for key, value in DEFAULT_CONFIG.items():
            print(f"{key}: {value}")
        print("\nAdmin Configuration:")
        print("-" * 20)
        for key, value in ADMIN_CONFIG.items():
            if key == "password":
                print(
                    f"{key}: {'*' * len(value) if value else 'Not set'}"
                )  # Hide password
            else:
                print(f"{key}: {value}")
        print("\nDefault Team Downloads:")
        print("-" * 25)
        for download in DEFAULT_TEAMDOWNLOADS:
            print(f"{download['filename']}: {download['description']}")

        print("\nDefault Flatpage Categories:")
        print("-" * 30)
        for category in DEFAULT_FLATPAGE_CATEGORIES:
            print(
                f"{category['title']} ({category['slug']}) - Order: {category['ordering']}"
            )

        print("\nDefault Flatpages:")
        print("-" * 20)
        for flatpage in DEFAULT_FLATPAGES:
            category = flatpage["category"] if flatpage["category"] else "No category"
            print(
                f"{flatpage['title']} ({flatpage['slug']}) - {flatpage['file_path']} [{category}]"
            )
        print()

    # Confirm reset
    print(f"This will perform a {args.reset_type.upper()} reset of the CTF gameserver.")
    if args.reset_type == "full":
        print(
            "WARNING: This will remove all teams, services, and reset all game settings!"
        )
    else:
        print(
            "This will clear all game data but keep teams, users, services, and sessions."
        )

    confirm = input("Are you sure you want to continue? (type 'yes' to confirm): ")
    if confirm.lower() != "yes":
        print("Reset cancelled.")
        sys.exit(0)

    # Connect to database
    conn = connect_to_database()

    try:
        # Perform reset
        if args.reset_type == "basic":
            basic_reset(conn)
        elif args.reset_type == "full":
            full_reset(conn)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
