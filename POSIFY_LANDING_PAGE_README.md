# Posify Modern SaaS Landing Page & Backend

## Overview

This is a complete redesign of the Posify landing page into a modern SaaS POS product website, built with React, Tailwind CSS, and Framer Motion on the frontend, and Python + Flask + PostgreSQL on the backend.

## Brand Identity

- **Primary Light Blue:** #3B82F6
- **Soft Orange:** #F97316
- **White Backgrounds**
- **Dark Text:** #0F172A

## Landing Page Sections

1. **Sticky Navigation Bar** - Blur effect on scroll, Posify logo, navigation links, Login and Start Free Trial buttons
2. **Hero Section** - Full-screen with headline "Simplify Sales. Grow Your Business.", POS terminal mockup with floating cards, trust indicators
3. **Features Section** - 8 premium feature cards with icons, hover animations, scroll animations
4. **Industries Section** - 7 industries with realistic photos and descriptions
5. **Dashboard Preview** - Realistic POS dashboard mockup with floating animation
6. **Testimonials** - Auto-scrolling customer review cards with photos and ratings
7. **Pricing Section** - 3 plans (Starter, Business, Enterprise) with Start Free Trial buttons
8. **CTA Section** - Contact form and business information
9. **Footer** - Links, social icons, and branding

## Backend Features

### Trial System
- 30-day free trial for each selected package
- Automatic trial record creation
- Trial end date tracking
- Automatic feature locking after trial expires

### Subscription System
- 30-day billing cycle
- Monthly subscription management
- Subscription status tracking
- Automatic renewal handling

### Payment Integration
- PesaPal API integration structure ready
- Payment status tracking
- Transaction reference storage
- Support for M-Pesa, cards, and bank transfers

### Posify Control Center (Admin Panel)
- Dashboard metrics: Total Businesses, Active Businesses, Trial Accounts, Expired Trials, Revenue, Subscription Renewals
- Business management: View all tenants, search businesses, suspend/activate accounts
- Trial management: View active and expired trials
- Subscription management: View all subscriptions
- Payment history: View all transactions
- Revenue analytics: Daily revenue charts and package distribution

## Project Structure

```
my-react-app/
  src/
    pages/
      LandingSaaS.jsx          # New modern landing page
      SubscriptionEnterprise.jsx # Updated trial/subscription page
      super-admin/
        PosifyControlCenter.jsx # Admin dashboard
        ControlCenterLogin.jsx  # Admin login
    components/
      landing/
        Navbar.jsx             # Sticky navigation
        Hero.jsx               # Hero section with POS mockup
        Features.jsx           # Feature cards
        Industries.jsx         # Industry showcase
        DashboardPreview.jsx   # Dashboard mockup
        Testimonials.jsx       # Auto-scrolling reviews
        Pricing.jsx            # Pricing plans
        CTASection.jsx         # Contact form
        Footer.jsx             # Footer
        ParallaxBackground.jsx # Parallax sections
    services/
      apiClient.js            # API client for backend
      mainAdminApi.js         # Admin API client

app.py                      # Flask application entrypoint
auth/
  service.py                # Authentication service
  manager.py                # JWT and session management
  decorators.py             # Route protection decorators
services/
  data_store.py             # Database abstraction layer
  session_store.py          # Session management
```

## Getting Started

### Frontend

```bash
cd my-react-app
npm install
npm run dev
```

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```env
DATABASE_URL=postgresql://user:pass@host/db
JWT_SECRET=your-secret-key-here
REFRESH_TOKEN_SECRET=your-refresh-secret-here
USE_POSTGRES=true
CORS_ORIGIN=http://localhost:5173
```

## Key Routes

### Frontend
- `/` - New SaaS Landing Page
- `/choose-subscription` - Trial/Subscription selection
- `/auth/login` - User login
- `/auth/signup` - User registration
- `/main.admin` - Posify Control Center (Owner only)
- `/super-admin/dashboard` - Posify Control Center (Legacy)

### Backend API
- `POST /api/auth/register` - Register business
- `POST /api/auth/login` - Login business
- `GET /api/auth/profile` - Get business profile
- `POST /api/trials/create` - Create trial
- `GET /api/trials/status` - Get trial status
- `GET /api/trials/active` - Get active trials
- `GET /api/trials/expired` - Get expired trials
- `POST /api/subscriptions/create` - Create subscription
- `GET /api/subscriptions/status` - Get subscription status
- `GET /api/subscriptions/all` - Get all subscriptions
- `POST /api/payments/initiate` - Initiate payment
- `POST /api/payments/status` - Update payment status
- `GET /api/admin/metrics` - Get dashboard metrics
- `GET /api/admin/businesses` - Get all businesses
- `POST /api/admin/businesses/:id/suspend` - Suspend business
- `POST /api/admin/businesses/:id/activate` - Activate business
- `GET /api/admin/revenue` - Get revenue analytics

## Tech Stack

- **Frontend:** React 18, Tailwind CSS 3, Framer Motion, Recharts
- **Backend:** Python 3.11, Flask, PostgreSQL
- **Authentication:** JWT (HS256) with refresh tokens
- **Payment:** Cash, Card, Bank Transfer

## Design Principles

- Professional and premium look
- Trustworthy and enterprise-ready
- Smooth animations and transitions
- Mobile-first responsive design
- No neon or glowing effects
- Clean, modern SaaS aesthetic comparable to Shopify, Square POS, Toast POS, and Lightspeed
