# Business Type Routing Fix

## Issue
When selecting a business type (clinic, bar, hotel) for Pro plan during subscription, users were still being redirected to the standard cashier dashboard instead of their business-specific dashboard after login.

## Root Cause
The business type selected during subscription wasn't being properly passed through the signup process and saved to the database, so during login the user object didn't have the businessType field needed for routing.

## Solution Applied

### 1. Frontend - Auth.jsx
**Fixed business type retrieval during signup:**
- Changed from `localStorage.getItem('selectedBusinessType')` to `localStorage.getItem('businessType')`
- This matches what Subscription.jsx stores
- Added logging to track the business type through the signup process
- Changed `businessType` to `business_type` in API call to match backend expectation

**File:** `/my-react-app/src/pages/Auth.jsx`

```javascript
// Get businessType from localStorage (set in Subscription.jsx)
const businessType = localStorage.getItem('businessType') || 
                     localStorage.getItem('selectedBusinessType') || 
                     selectedPlan?.business_type;

console.log('[SIGNUP] Plan:', planId, 'BusinessType:', businessType);

res = await auth.signup({
  email: formData.email,
  password: formData.password,
  name: formData.name,
  plan: planId,
  business_type: businessType,  // Use underscore to match backend
  selectedFeatures: selectedFeatures ? JSON.parse(selectedFeatures) : []
});
```

### 2. Backend - auth_controller.py
**Updated signup method to accept and store business_type:**
- Added `business_type` parameter to signup method
- Store business_type directly in user record during signup
- Add businessType to response so frontend knows about it immediately
- Added default business_role as 'admin' for new signups

**File:** `/backend/auth_controller.py`

```python
def signup(self, email: str, password: str, name: str, plan: str = 'free', 
           is_main_admin: bool = False, business_type: Optional[str] = None):
    # ... existing code ...
    
    user_data = {
        'account_id': account_id,
        'email': email,
        'password_hash': self.hash_password(password),
        'name': name,
        'role': user_role,
        'is_active': True,
        'is_locked': False,
        'screen_locked': False,
        'created_at': datetime.now().isoformat(),
        'last_login': datetime.now().isoformat(),
        'hourly_rate': 0.0,
        'business_type': business_type,  # NEW
        'business_role': 'admin'         # NEW
    }
    
    # Add to response for frontend
    if business_type:
        user_response['businessType'] = business_type
```

### 3. Backend - app.py
**Updated signup endpoint to pass business_type:**
- Added logging to track business_type in requests
- Pass business_type to auth.signup() method

**File:** `/backend/app.py`

```python
@app.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    plan = data.get('plan', 'free')
    is_main_admin = data.get('is_main_admin', False)
    business_type = data.get('business_type')  # Get from request
    
    logger.info(f"📝 Signup request - Plan: {plan}, Business Type: {business_type}")
    
    # Pass business_type to signup method
    success, error, response = auth.signup(email, password, name, plan, 
                                          is_main_admin, business_type)
```

### 4. Frontend - ProPlanRouter.jsx
**Enhanced business type detection:**
- Check multiple sources for business type
- Check both camelCase and snake_case versions
- Added more detailed logging

**File:** `/my-react-app/src/pages/ProPlanRouter.jsx`

```javascript
// Get business context - check multiple sources
const businessType = user.businessType || 
                     user.business_type || 
                     localStorage.getItem('businessType') || 
                     localStorage.getItem('selectedBusinessType');
const businessRole = user.businessRole || user.business_role || user.role;

console.log('[PRO PLAN ROUTER] Business Type:', businessType, 'Role:', businessRole, 'User:', user);
```

## Flow After Fix

### Signup Flow
```
1. User selects Pro plan → /choose-subscription
2. User selects business type (e.g., "clinic")
3. localStorage.setItem('businessType', 'clinic')
4. User goes to /auth/signup
5. Auth.jsx retrieves businessType from localStorage
6. Sends to backend: { plan: 'pro', business_type: 'clinic' }
7. Backend saves to user.business_type = 'clinic'
8. Backend creates business_profile with business_type
9. Backend returns user with businessType = 'clinic'
10. Frontend redirects to /pro-dashboard
11. ProPlanRouter sees businessType = 'clinic'
12. Routes to ClinicDashboard (or specific role dashboard)
```

### Login Flow
```
1. User logs in with email/password
2. Backend retrieves user from database
3. User has business_type = 'clinic' in database
4. Backend returns user with businessType = 'clinic'
5. Frontend Auth.jsx checks: plan='pro' && businessType='clinic'
6. Redirects to /pro-dashboard
7. ProPlanRouter sees businessType = 'clinic'
8. Routes to ClinicDashboard
```

## Testing

### Test Case 1: Pro Plan - Clinic
```
1. Go to /choose-subscription
2. Select "Pro" plan
3. Click "Get Started"
4. Select "Clinic" business type
5. Fill signup form and submit
6. ✅ Should redirect to clinic dashboard
7. Logout
8. Login again
9. ✅ Should redirect to clinic dashboard
```

### Test Case 2: Pro Plan - Bar
```
1. Go to /choose-subscription
2. Select "Pro" plan
3. Click "Get Started"
4. Select "Bar/Restaurant" business type
5. Fill signup form and submit
6. ✅ Should redirect to bar dashboard
7. Logout
8. Login again
9. ✅ Should redirect to bar dashboard
```

### Test Case 3: Pro Plan - Hotel
```
1. Go to /choose-subscription
2. Select "Pro" plan
3. Click "Get Started"
4. Select "Hotel" business type
5. Fill signup form and submit
6. ✅ Should redirect to hotel dashboard
7. Logout
8. Login again
9. ✅ Should redirect to hotel dashboard
```

### Test Case 4: Basic/Ultra Plans (Should still work)
```
1. Go to /choose-subscription
2. Select "Basic" or "Ultra" plan
3. Click "Get Started"
4. Fill signup form (no business type selection)
5. ✅ Should redirect to standard admin dashboard
6. Logout
7. Login again
8. ✅ Should redirect to standard admin dashboard
```

## Database Schema
The business_type is now stored in two places:
1. **users table**: `business_type` column (for immediate availability)
2. **business_profiles table**: `business_type` field (for Pro plan settings)

This dual storage ensures:
- Quick access during login (from users table)
- Business configuration storage (business_profiles table)
- Backward compatibility with existing code

## Files Modified
1. `/my-react-app/src/pages/Auth.jsx` - Fixed businessType retrieval and API call
2. `/backend/auth_controller.py` - Updated signup to accept and store business_type
3. `/backend/app.py` - Updated signup endpoint to pass business_type
4. `/my-react-app/src/pages/ProPlanRouter.jsx` - Enhanced business type detection

## Summary
The fix ensures that when a Pro plan user selects a business type during subscription:
1. It's properly stored in localStorage
2. Passed to the backend during signup
3. Saved to the database in the user record
4. Returned in login responses
5. Used for routing to the correct dashboard

**Status:** ✅ Fixed and Ready for Testing
**Date:** January 27, 2026
