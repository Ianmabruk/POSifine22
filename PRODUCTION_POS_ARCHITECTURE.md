# 🏗️ PRODUCTION POS SYSTEM - COMPREHENSIVE ARCHITECTURE REFACTOR

## Phase 1: Architecture Blueprint

### Current State Analysis
- ✅ Python Flask backend with PostgreSQL
- ✅ React frontend with Vite
- ✅ Basic auth & JWT implemented
- ⚠️ Admin/Cashier dashboards exist but not fully integrated
- ⚠️ Stock deduction logic exists but needs atomic transactions
- ⚠️ No proper real-time sync (monitor dashboard)
- ⚠️ No shift management (clock in/out)
- ⚠️ Plans (Basic/Ultra/Custom) not properly routed to different dashboards

### What Needs to Be Built

#### 1. PLAN-BASED ROUTING (Core Flow)

```
USER SIGNUP
    ↓
SELECT PLAN
    ↓
    ├─ BASIC (1000 KES) ──→ GENERIC ADMIN DASHBOARD
    │
    ├─ ULTRA (2500 KES) ──→ GENERIC ADMIN DASHBOARD (Enhanced)
    │
    └─ CUSTOM (3500 KES) ──→ SELECT BUSINESS TYPE
                                ↓
                        ┌───────┬────────┬──────────┬──────┬────────┐
                        ↓       ↓        ↓          ↓      ↓        ↓
                      Bar    Hospital School      Kiosk  Petrol  Shoes
                        ↓       ↓        ↓          ↓      ↓        ↓
                    BUSINESS-SPECIFIC ADMIN DASHBOARDS
```

#### 2. DATABASE SCHEMA (PostgreSQL)

```sql
-- Core Tables
users (id, email, password, name, role, plan, businessType, accountId, active)
roles (id, name, permissions[])
products (id, name, price, category, stock, businessType)
sales (id, userId, items[], totalAmount, discount, tax, businessType, createdAt)
stockLogs (id, productId, quantity, type[add/deduct], reason, userId, createdAt)
expenses (id, description, amount, category, userId, createdAt)
shifts (id, userId, clockInTime, clockOutTime, totalSales, status)
businessModules (businessType, features[])

-- Business-Specific Tables
(hospital_services, hospital_medicines, hospital_patients, hospital_staff)
(school_students, school_fees, school_classes)
(petrol_pumps, petrol_tanks, petrol_shifts)
(etc...)
```

#### 3. AUTHENTICATION & ROLES

Role Hierarchy:
```
Owner/Admin
  ├─ Cashier (Can: Sell, Clock In/Out, View Monitor)
  ├─ Staff/Worker (Can: Limited actions)
  └─ Manager (Can: View Reports, Approve)

JWT Token Structure:
{
  sub: userId,
  role: 'admin|cashier|staff',
  plan: 'basic|ultra|custom',
  businessType: 'bar|hospital|school|...',
  permissions: ['sell', 'clock', 'view_reports']
}
```

#### 4. REAL-TIME SYNC STRATEGY

```
Frontend Action
    ↓
Backend Transaction (locked)
    ↓
Database Commit
    ↓
Broadcast Update (WebSocket)
    ↓
All Connected Clients Update UI
```

---

## Phase 2: Implementation Roadmap

### STEP 1: Backend Database Schema (Core)
- [ ] Create migrations for all tables
- [ ] Add transaction support
- [ ] Create indexes for performance

### STEP 2: Backend API Endpoints
- [ ] Auth endpoints (login, signup, verify)
- [ ] Product CRUD + Stock management
- [ ] Sales endpoint (atomic transaction)
- [ ] Shift management (clock in/out)
- [ ] Monitor endpoints (real-time aggregation)
- [ ] Expense tracking

### STEP 3: Frontend Auth & Navigation
- [ ] Fix plan-based routing logic
- [ ] Implement role guards
- [ ] Create proper redirects post-signup

### STEP 4: Generic Admin Dashboard (Basic & Ultra)
- [ ] Users management
- [ ] Products/Inventory
- [ ] Sales history
- [ ] Expenses
- [ ] Reports
- [ ] Stock logs
- [ ] Roles & Permissions

### STEP 5: Business-Specific Admin Dashboards (Custom)
- [ ] Bar: Drinks, Brands, Staff Shifts, Happy Hour Pricing
- [ ] Hospital: Services, Medicines, Patients, Billing
- [ ] School: Students, Fees, Classes, Term Reports
- [ ] Kiosk: Products, Suppliers, Pricing
- [ ] Petrol: Pumps, Tanks, Fuel Types, Shift Reconciliation
- [ ] Shoes: Variants, Margins, Returns

### STEP 6: Cashier Dashboards (All Business Types)
- [ ] Generic Cashier (for Basic/Ultra)
- [ ] Bar Cashier (categories, drinks)
- [ ] Hospital Cashier (patient search, services)
- [ ] School Cashier (student lookup, fees)
- [ ] Kiosk Cashier (fast search/click POS)
- [ ] Petrol Cashier (pump selector, liters)
- [ ] Shoes Cashier (variant selector, barcode)

### STEP 7: Core Features Implementation
- [ ] Stock deduction (atomic, real-time)
- [ ] Discount & tax calculation
- [ ] Clock in/out system
- [ ] Monitor dashboard (real-time)
- [ ] Receipt printing

### STEP 8: Performance & Testing
- [ ] Optimize Complete Sale (< 100ms)
- [ ] Stress test concurrent users
- [ ] End-to-end flow verification
- [ ] Real-time sync validation

---

## Phase 3: Detailed Component Specs

### Admin Dashboard Structure
```
/src/pages/admin/
  ├─ AdminDashboard.jsx (generic for Basic/Ultra)
  ├─ BarAdminDashboard.jsx
  ├─ HospitalAdminDashboard.jsx
  ├─ SchoolAdminDashboard.jsx
  ├─ KioskAdminDashboard.jsx
  ├─ PetrolAdminDashboard.jsx
  ├─ ShoeAdminDashboard.jsx
  └─ modules/
      ├─ UsersManager.jsx
      ├─ ProductsManager.jsx
      ├─ SalesHistory.jsx
      ├─ ExpensesManager.jsx
      └─ ReportsViewer.jsx
```

### Cashier Dashboard Structure
```
/src/pages/cashier/
  ├─ CashierPOS.jsx (generic)
  ├─ BarCashierPOS.jsx
  ├─ HospitalCashierPOS.jsx
  ├─ SchoolCashierPOS.jsx
  ├─ KioskCashierPOS.jsx
  ├─ PetrolCashierPOS.jsx
  ├─ ShoeCashierPOS.jsx
  └─ common/
      ├─ MonitorDashboard.jsx
      ├─ ClockInOut.jsx
      └─ CompleteSaleFlow.jsx
```

---

## Implementation Status

- [x] Business types defined (6 types)
- [x] Admin dashboards created (6 dashboards)
- [ ] **Next: Backend API refactor for atomic transactions**
- [ ] **Next: Proper routing logic for plans**
- [ ] **Next: Cashier dashboards implementation**
- [ ] **Next: Real-time sync with WebSocket**

---

## Key Performance Requirements

```
Complete Sale:           < 100ms
Stock Deduction:         < 50ms
Monitor Update:          Real-time (< 1s)
Clock In/Out:            < 200ms
Dashboard Load:          < 2s
```

---

## Next Actions

1. **Audit database schema** - verify all tables exist
2. **Create migration files** - for any missing tables
3. **Refactor Complete Sale endpoint** - add transaction locks
4. **Implement proper routing** - plans → dashboards
5. **Create role guards** - frontend & backend
6. **Build monitor dashboard** - real-time sync
7. **Implement shift management** - clock in/out
