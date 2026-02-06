"""
BUSINESS TYPE CONFIGURATION
===========================
Configuration for Pro and Custom subscription business types.
Defines available business types, roles, and permissions for each type.
"""

from typing import Dict, List, Any
from enum import Enum


class BusinessType(Enum):
    """Available business types for Pro/Custom subscriptions"""
    BAR = "bar"
    HOTEL = "hotel"
    CLINIC = "clinic"
    HOSPITAL = "hospital"
    SUPERMARKET = "supermarket"
    RESTAURANT = "restaurant"
    PHARMACY = "pharmacy"
    PETROL_STATION = "petrol"
    SCHOOL = "school"
    KIOSK = "kiosk"
    SHOES = "shoes"
    GYM = "gym"
    SALON = "salon"
    RETAIL = "retail"


# Business type configurations with roles, features, and permissions
BUSINESS_TYPES_CONFIG: Dict[str, Dict[str, Any]] = {
    "bar": {
        "id": "bar",
        "name": "Bar/Restaurant",
        "description": "Bar and restaurant management with table service and inventory",
        "icon": "Utensils",
        "roles": [
            {
                "id": "admin",
                "name": "Manager",
                "permissions": ["manage_inventory", "view_reports", "manage_staff", "manage_tables"]
            },
            {
                "id": "bartender",
                "name": "Bartender",
                "permissions": ["create_orders", "view_inventory", "process_payments"]
            },
            {
                "id": "waiter",
                "name": "Waiter",
                "permissions": ["create_orders", "manage_tables", "view_menu"]
            },
            {
                "id": "cashier",
                "name": "Cashier",
                "permissions": ["process_payments", "view_sales"]
            }
        ],
        "features": [
            "Table Management",
            "Drink & Food Inventory",
            "Split Bills",
            "Tips Tracking",
            "Shift Management",
            "Bar Stock Alerts"
        ],
        "dashboard_route": "/pro-dashboard/bar"
    },
    
    "hotel": {
        "id": "hotel",
        "name": "Hotel",
        "description": "Hotel management with room booking and guest services",
        "icon": "Hotel",
        "roles": [
            {
                "id": "admin",
                "name": "Hotel Manager",
                "permissions": ["manage_rooms", "view_reports", "manage_staff", "manage_bookings"]
            },
            {
                "id": "reception",
                "name": "Receptionist",
                "permissions": ["manage_bookings", "check_in", "check_out", "view_rooms"]
            },
            {
                "id": "housekeeping",
                "name": "Housekeeping",
                "permissions": ["update_room_status", "view_schedule"]
            },
            {
                "id": "cashier",
                "name": "Cashier",
                "permissions": ["process_payments", "view_bills"]
            }
        ],
        "features": [
            "Room Booking Management",
            "Check-in/Check-out",
            "Housekeeping Status",
            "Guest Services Tracking",
            "Room Service Orders",
            "Revenue Reports"
        ],
        "dashboard_route": "/pro-dashboard/hotel"
    },
    
    "clinic": {
        "id": "clinic",
        "name": "Clinic",
        "description": "Medical clinic with patient management and pharmacy",
        "icon": "Stethoscope",
        "roles": [
            {
                "id": "admin",
                "name": "Clinic Manager",
                "permissions": ["manage_staff", "view_reports", "manage_inventory", "manage_patients"]
            },
            {
                "id": "doctor",
                "name": "Doctor",
                "permissions": ["view_patients", "prescribe", "view_medical_records", "create_appointments"]
            },
            {
                "id": "nurse",
                "name": "Nurse",
                "permissions": ["view_patients", "update_vitals", "view_appointments"]
            },
            {
                "id": "reception",
                "name": "Receptionist",
                "permissions": ["register_patients", "manage_appointments", "process_payments"]
            },
            {
                "id": "pharmacy",
                "name": "Pharmacist",
                "permissions": ["dispense_medication", "manage_pharmacy_stock", "view_prescriptions"]
            }
        ],
        "features": [
            "Patient Registration",
            "Appointment Scheduling",
            "Medical Records",
            "Prescription Management",
            "Pharmacy Inventory",
            "Billing & Insurance"
        ],
        "dashboard_route": "/pro-dashboard/clinic"
    },
    
    "hospital": {
        "id": "hospital",
        "name": "Hospital",
        "description": "Full hospital management with departments and services",
        "icon": "Building2",
        "roles": [
            {
                "id": "admin",
                "name": "Hospital Administrator",
                "permissions": ["manage_all", "view_all_reports", "manage_departments"]
            },
            {
                "id": "doctor",
                "name": "Doctor",
                "permissions": ["view_patients", "prescribe", "admit_patients", "discharge_patients"]
            },
            {
                "id": "nurse",
                "name": "Nurse",
                "permissions": ["view_patients", "update_records", "administer_medication"]
            },
            {
                "id": "reception",
                "name": "Receptionist",
                "permissions": ["register_patients", "manage_appointments", "direct_patients"]
            },
            {
                "id": "pharmacy",
                "name": "Pharmacist",
                "permissions": ["dispense_medication", "manage_pharmacy_stock"]
            },
            {
                "id": "lab",
                "name": "Lab Technician",
                "permissions": ["record_tests", "view_test_requests"]
            }
        ],
        "features": [
            "Patient Admission/Discharge",
            "Department Management",
            "Bed Management",
            "Lab Test Tracking",
            "Surgery Scheduling",
            "Pharmacy & Inventory"
        ],
        "dashboard_route": "/pro-dashboard/hospital"
    },
    
    "supermarket": {
        "id": "supermarket",
        "name": "Supermarket/Retail",
        "description": "Retail supermarket with product scanning and inventory",
        "icon": "ShoppingCart",
        "roles": [
            {
                "id": "admin",
                "name": "Store Manager",
                "permissions": ["manage_inventory", "view_reports", "manage_staff", "manage_suppliers"]
            },
            {
                "id": "cashier",
                "name": "Cashier",
                "permissions": ["process_sales", "scan_products", "process_payments"]
            },
            {
                "id": "stock_clerk",
                "name": "Stock Clerk",
                "permissions": ["update_inventory", "receive_stock", "stock_check"]
            }
        ],
        "features": [
            "Barcode Scanning",
            "Product Inventory",
            "Stock Alerts",
            "Supplier Management",
            "Sales Analytics",
            "Loyalty Programs"
        ],
        "dashboard_route": "/pro-dashboard/supermarket"
    },

    "kiosk": {
        "id": "kiosk",
        "name": "Kiosk/Mini Shop",
        "description": "Small retail kiosk with fast sales and stock tracking",
        "icon": "Store",
        "roles": [
            {
                "id": "admin",
                "name": "Kiosk Owner",
                "permissions": ["manage_inventory", "view_reports", "manage_staff"]
            },
            {
                "id": "cashier",
                "name": "Cashier",
                "permissions": ["process_sales", "process_payments", "view_stock"]
            }
        ],
        "features": [
            "Quick Sales",
            "Stock Alerts",
            "Daily Summary",
            "Supplier Tracking"
        ],
        "dashboard_route": "/pro-dashboard/kiosk"
    },

    "shoes": {
        "id": "shoes",
        "name": "Shoe Store",
        "description": "Shoe retail with size variants and inventory tracking",
        "icon": "ShoppingCart",
        "roles": [
            {
                "id": "admin",
                "name": "Store Manager",
                "permissions": ["manage_inventory", "view_reports", "manage_staff", "manage_suppliers"]
            },
            {
                "id": "cashier",
                "name": "Cashier",
                "permissions": ["process_sales", "process_payments", "view_stock"]
            },
            {
                "id": "stock_clerk",
                "name": "Stock Clerk",
                "permissions": ["update_inventory", "receive_stock", "stock_check"]
            }
        ],
        "features": [
            "Size Variants",
            "Supplier Management",
            "Stock Alerts",
            "Sales Analytics"
        ],
        "dashboard_route": "/pro-dashboard/shoes"
    },
    
    "restaurant": {
        "id": "restaurant",
        "name": "Restaurant",
        "description": "Restaurant management with kitchen and table service",
        "icon": "ChefHat",
        "roles": [
            {
                "id": "admin",
                "name": "Restaurant Manager",
                "permissions": ["manage_menu", "view_reports", "manage_staff", "manage_inventory"]
            },
            {
                "id": "chef",
                "name": "Chef",
                "permissions": ["view_orders", "update_order_status", "manage_recipes"]
            },
            {
                "id": "waiter",
                "name": "Waiter",
                "permissions": ["create_orders", "manage_tables", "view_menu"]
            },
            {
                "id": "cashier",
                "name": "Cashier",
                "permissions": ["process_payments", "view_bills"]
            }
        ],
        "features": [
            "Menu Management",
            "Kitchen Display System",
            "Table Reservations",
            "Recipe & Ingredients",
            "Order Tracking",
            "Customer Feedback"
        ],
        "dashboard_route": "/pro-dashboard/restaurant"
    },
    
    "pharmacy": {
        "id": "pharmacy",
        "name": "Pharmacy",
        "description": "Pharmacy with prescription management and drug inventory",
        "icon": "Pill",
        "roles": [
            {
                "id": "admin",
                "name": "Pharmacy Manager",
                "permissions": ["manage_inventory", "view_reports", "manage_staff", "manage_suppliers"]
            },
            {
                "id": "pharmacist",
                "name": "Pharmacist",
                "permissions": ["dispense_medication", "verify_prescriptions", "counsel_patients"]
            },
            {
                "id": "cashier",
                "name": "Cashier",
                "permissions": ["process_payments", "view_stock"]
            }
        ],
        "features": [
            "Prescription Verification",
            "Drug Inventory",
            "Expiry Tracking",
            "Patient Counseling Records",
            "Insurance Claims",
            "Controlled Substances Tracking"
        ],
        "dashboard_route": "/pro-dashboard/pharmacy"
    },
    
    "petrol": {
        "id": "petrol",
        "name": "Petrol Station",
        "description": "Petrol station with pump tracking and fuel inventory",
        "icon": "Fuel",
        "roles": [
            {
                "id": "admin",
                "name": "Station Manager",
                "permissions": ["manage_pumps", "view_reports", "manage_staff", "reconcile_shifts"]
            },
            {
                "id": "attendant",
                "name": "Pump Attendant",
                "permissions": ["record_sales", "view_pump_readings"]
            },
            {
                "id": "cashier",
                "name": "Cashier",
                "permissions": ["process_payments", "end_shift"]
            }
        ],
        "features": [
            "Pump Tracking",
            "Fuel Tank Monitoring",
            "Shift Reconciliation",
            "Fuel Delivery Management",
            "Credit Sales",
            "Dip Reading Records"
        ],
        "dashboard_route": "/pro-dashboard/petrol"
    },
    
    "school": {
        "id": "school",
        "name": "School",
        "description": "School management with fees, canteen, and student services",
        "icon": "GraduationCap",
        "roles": [
            {
                "id": "admin",
                "name": "School Administrator",
                "permissions": ["manage_students", "view_reports", "manage_staff", "manage_fees"]
            },
            {
                "id": "accountant",
                "name": "Accountant",
                "permissions": ["manage_fees", "view_payments", "generate_invoices"]
            },
            {
                "id": "canteen",
                "name": "Canteen Staff",
                "permissions": ["process_sales", "manage_menu", "view_inventory"]
            }
        ],
        "features": [
            "Student Management",
            "Fee Collection",
            "Canteen POS",
            "Uniform & Books Sales",
            "Payment Tracking",
            "Term Reports"
        ],
        "dashboard_route": "/pro-dashboard/school"
    },
    
    "gym": {
        "id": "gym",
        "name": "Gym/Fitness Center",
        "description": "Gym management with memberships and class scheduling",
        "icon": "Dumbbell",
        "roles": [
            {
                "id": "admin",
                "name": "Gym Manager",
                "permissions": ["manage_members", "view_reports", "manage_staff", "manage_classes"]
            },
            {
                "id": "trainer",
                "name": "Trainer",
                "permissions": ["view_clients", "schedule_sessions", "track_progress"]
            },
            {
                "id": "reception",
                "name": "Receptionist",
                "permissions": ["register_members", "process_payments", "manage_bookings"]
            }
        ],
        "features": [
            "Membership Management",
            "Class Scheduling",
            "Personal Training Sessions",
            "Equipment Tracking",
            "Attendance Records",
            "Subscription Renewals"
        ],
        "dashboard_route": "/pro-dashboard/gym"
    },
    
    "salon": {
        "id": "salon",
        "name": "Salon/Spa",
        "description": "Salon and spa management with appointments and services",
        "icon": "Scissors",
        "roles": [
            {
                "id": "admin",
                "name": "Salon Manager",
                "permissions": ["manage_staff", "view_reports", "manage_services", "manage_products"]
            },
            {
                "id": "stylist",
                "name": "Stylist",
                "permissions": ["view_appointments", "process_services", "view_products"]
            },
            {
                "id": "reception",
                "name": "Receptionist",
                "permissions": ["manage_appointments", "process_payments", "register_clients"]
            }
        ],
        "features": [
            "Appointment Booking",
            "Service Menu",
            "Product Sales",
            "Stylist Commission",
            "Client History",
            "Package Deals"
        ],
        "dashboard_route": "/pro-dashboard/salon"
    },
    
    "retail": {
        "id": "retail",
        "name": "General Retail",
        "description": "General retail store management",
        "icon": "Store",
        "roles": [
            {
                "id": "admin",
                "name": "Store Manager",
                "permissions": ["manage_inventory", "view_reports", "manage_staff"]
            },
            {
                "id": "cashier",
                "name": "Cashier",
                "permissions": ["process_sales", "process_payments"]
            }
        ],
        "features": [
            "Product Management",
            "Sales Processing",
            "Inventory Tracking",
            "Customer Records",
            "Reports & Analytics"
        ],
        "dashboard_route": "/pro-dashboard/retail"
    }
}


def get_business_type_config(business_type: str) -> Dict[str, Any]:
    """Get configuration for a specific business type"""
    return BUSINESS_TYPES_CONFIG.get(business_type, BUSINESS_TYPES_CONFIG["retail"])


def get_available_business_types() -> List[Dict[str, Any]]:
    """Get list of all available business types"""
    return [
        {
            "id": config["id"],
            "name": config["name"],
            "description": config["description"],
            "icon": config["icon"]
        }
        for config in BUSINESS_TYPES_CONFIG.values()
    ]


def get_roles_for_business_type(business_type: str) -> List[Dict[str, Any]]:
    """Get available roles for a specific business type"""
    config = get_business_type_config(business_type)
    return config.get("roles", [])


def validate_business_role(business_type: str, role: str) -> bool:
    """Validate if a role is valid for the given business type"""
    roles = get_roles_for_business_type(business_type)
    return any(r["id"] == role for r in roles)


def get_features_for_business_type(business_type: str) -> List[str]:
    """Get features available for a specific business type"""
    config = get_business_type_config(business_type)
    return config.get("features", [])


def get_dashboard_route(business_type: str) -> str:
    """Get the dashboard route for a specific business type"""
    config = get_business_type_config(business_type)
    return config.get("dashboard_route", "/admin")
