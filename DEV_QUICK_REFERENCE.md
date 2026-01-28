# 🚀 Pro Plan System - Developer Quick Reference

## Adding a New Business Type

### 1. Update Routing Utility

**File**: `my-react-app/src/utils/dashboardRouting.js`

```javascript
// Add to getDashboardRoute() function
if (businessType === 'newbusiness') {
  return `/admin/newbusiness`;
}
```

### 2. Create Admin Dashboard

**File**: `my-react-app/src/pages/admin/AdminNewBusinessDashboard.jsx`

```javascript
import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';

export default function AdminNewBusinessDashboard() {
  const { user } = useAuth();
  const [staff, setStaff] = useState([]);
  
  const roles = [
    { value: 'role1', label: 'Role 1', icon: Icon1 },
    { value: 'role2', label: 'Role 2', icon: Icon2 }
  ];
  
  // Copy structure from AdminClinicDashboard.jsx
  // Customize roles and business logic
  
  return <div>Your dashboard here</div>;
}
```

### 3. Create Role Dashboards

**File**: `my-react-app/src/pages/dashboards/newbusiness/Role1Dashboard.jsx`

```javascript
import { useState, useEffect } from 'react';
import { useAuth } from '../../../context/AuthContext';
import api from '../../../services/api';

export default function Role1Dashboard() {
  // Copy structure from ClinicDoctorDashboard.jsx
  // Customize for your role
}
```

### 4. Add Routes

**File**: `my-react-app/src/App.jsx`

```javascript
import AdminNewBusinessDashboard from './pages/admin/AdminNewBusinessDashboard';
import Role1Dashboard from './pages/dashboards/newbusiness/Role1Dashboard';

// Inside Routes:
<Route path="/admin/newbusiness" element={
  <RouteGuard>
    <ProPlanGuard>
      <BusinessTypeGuard requiredType="newbusiness">
        <AdminGuard>
          <AdminNewBusinessDashboard />
        </AdminGuard>
      </BusinessTypeGuard>
    </ProPlanGuard>
  </RouteGuard>
} />

<Route path="/dashboard/newbusiness/role1" element={
  <RouteGuard>
    <ProPlanGuard>
      <BusinessTypeGuard requiredType="newbusiness">
        <RoleGuard allowedRoles={['role1']}>
          <Role1Dashboard />
        </RoleGuard>
      </BusinessTypeGuard>
    </ProPlanGuard>
  </RouteGuard>
} />
```

### 5. Update Messaging Permissions

**File**: `backend/message_routes.py`

Find the `role_permissions` dictionary in `get_available_roles()`:

```python
role_permissions = {
    'newbusiness': {
        'role1': ['role2', 'role3'],
        'role2': ['role1'],
        'role3': ['role1', 'role2'],
        'admin': ['role1', 'role2', 'role3']
    }
}
```

---

## Adding a New Role to Existing Business

### 1. Update Admin Dashboard

**File**: `my-react-app/src/pages/admin/AdminClinicDashboard.jsx`

```javascript
const clinicRoles = [
  // ... existing roles ...
  { value: 'newrole', label: 'New Role', icon: IconName }
];
```

### 2. Create Role Dashboard

**File**: `my-react-app/src/pages/dashboards/clinic/NewRoleDashboard.jsx`

```javascript
export default function NewRoleDashboard() {
  // Implementation
}
```

### 3. Add Route

**File**: `my-react-app/src/App.jsx`

```javascript
<Route path="/dashboard/clinic/newrole" element={
  <RouteGuard>
    <ProPlanGuard>
      <BusinessTypeGuard requiredType="clinic">
        <RoleGuard allowedRoles={['newrole']}>
          <NewRoleDashboard />
        </RoleGuard>
      </BusinessTypeGuard>
    </ProPlanGuard>
  </RouteGuard>
} />
```

### 4. Update Messaging Permissions

**File**: `backend/message_routes.py`

```python
'clinic': {
    # ... existing roles ...
    'newrole': ['doctor', 'registrar'],  # Who newrole can message
    'doctor': ['registrar', 'pharmacist', 'newrole'],  # Update others
}
```

---

## API Endpoints

### Messaging

```javascript
// Send message
POST /api/messages/send
{
  "toRole": "pharmacist",
  "content": "Message text",
  "priority": "normal" | "urgent"
}

// Get inbox
GET /api/messages/inbox?status=unread&limit=50

// Get sent messages
GET /api/messages/sent?limit=50

// Mark as read
PUT /api/messages/{messageId}/read

// Get available roles to message
GET /api/messages/available-roles
```

### User Management

```javascript
// Get staff
GET /api/business/users

// Add staff
POST /api/business/users
{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "password123",
  "businessRole": "doctor"
}

// Update staff
PUT /api/business/users/{userId}

// Delete staff
DELETE /api/business/users/{userId}
```

---

## Common Patterns

### Protected Page Component

```javascript
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

export default function MyDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const response = await api.get('/api/endpoint');
      setData(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Failed to load:', error);
      setLoading(false);
    }
  };

  if (loading) return <div>Loading...</div>;

  return <div>Your content</div>;
}
```

### Send Message Button

```javascript
const [showSendMessage, setShowSendMessage] = useState(false);

<button onClick={() => setShowSendMessage(true)}>
  Send Message
</button>

{showSendMessage && (
  <SendMessageModal onClose={() => setShowSendMessage(false)} />
)}
```

### Message Inbox Component

```javascript
const [messages, setMessages] = useState([]);
const [unreadCount, setUnreadCount] = useState(0);

useEffect(() => {
  loadMessages();
  // Optional: Poll every 30 seconds
  const interval = setInterval(loadMessages, 30000);
  return () => clearInterval(interval);
}, []);

const loadMessages = async () => {
  const response = await api.get('/api/messages/inbox');
  setMessages(response.data.messages || []);
  setUnreadCount(response.data.unreadCount || 0);
};

const markAsRead = async (messageId) => {
  await api.put(`/api/messages/${messageId}/read`);
  loadMessages();
};
```

---

## Route Guard Examples

### Require Authentication Only
```javascript
<RouteGuard>
  <MyComponent />
</RouteGuard>
```

### Require Pro Plan
```javascript
<RouteGuard>
  <ProPlanGuard>
    <MyComponent />
  </ProPlanGuard>
</RouteGuard>
```

### Require Specific Role
```javascript
<RouteGuard>
  <RoleGuard allowedRoles={['admin', 'manager']}>
    <MyComponent />
  </RoleGuard>
</RouteGuard>
```

### Require Business Type
```javascript
<RouteGuard>
  <BusinessTypeGuard requiredType="clinic">
    <MyComponent />
  </BusinessTypeGuard>
</RouteGuard>
```

### Full Stack (Most Secure)
```javascript
<RouteGuard>
  <ProPlanGuard>
    <BusinessTypeGuard requiredType="clinic">
      <RoleGuard allowedRoles={['doctor']}>
        <MyComponent />
      </RoleGuard>
    </BusinessTypeGuard>
  </ProPlanGuard>
</RouteGuard>
```

---

## User Object Structure

```javascript
{
  id: 'user_1',
  name: 'Dr. Smith',
  email: 'doctor@clinic.com',
  role: 'cashier',              // Base system role
  businessRole: 'doctor',       // Specific business role
  businessType: 'clinic',       // Business type
  subscription: 'pro',          // Subscription plan
  plan: 'pro',                  // Alias for subscription
  account_id: 'account_1',
  is_active: true
}
```

---

## Debugging Tips

### Check User Routing
```javascript
import { debugRoutingDecision } from './utils/dashboardRouting';

// In component
debugRoutingDecision(user);
// Logs user details and calculated route
```

### Check API Calls
```javascript
// In browser console
localStorage.getItem('token')  // Check token exists
console.log(user)              // Check user object
```

### Test Message Sending
```bash
curl -X POST http://localhost:5000/api/messages/send \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"toRole":"pharmacist","content":"Test message"}'
```

### Check Backend Logs
```bash
cd backend
python app.py
# Look for: ✅ Internal messaging routes registered
```

---

## Troubleshooting

### "Access Denied" on Dashboard
- Check user has correct `businessType`
- Check user has correct `businessRole`
- Check route guard requirements
- Check user subscription is 'pro'

### Messages Not Showing
- Check backend message routes are registered
- Check user has `businessType` set
- Check message permissions in `message_routes.py`
- Check API token is valid

### User Not Routing Correctly
- Check `dashboardRouting.js` logic
- Use `debugRoutingDecision(user)` to see calculation
- Check user object has all required fields
- Check route guards are not blocking access

---

## Testing Checklist

### New Business Type
- [ ] Admin dashboard shows
- [ ] Can add staff with roles
- [ ] Staff appears in list
- [ ] Staff can login
- [ ] Staff routes to correct dashboard
- [ ] Messages work between roles
- [ ] Route guards work correctly

### New Role
- [ ] Appears in admin dropdown
- [ ] Can be assigned to user
- [ ] User routes to role dashboard
- [ ] Can send/receive messages
- [ ] Only sees allowed recipients

---

## Performance Tips

1. **Lazy Load Dashboards**
   ```javascript
   const AdminClinicDashboard = lazy(() => 
     import('./pages/admin/AdminClinicDashboard')
   );
   ```

2. **Debounce API Calls**
   ```javascript
   const debouncedLoad = debounce(loadData, 300);
   ```

3. **Cache Messages**
   ```javascript
   const [messageCache, setMessageCache] = useState({});
   ```

4. **Paginate Staff List**
   ```javascript
   GET /api/business/users?page=1&limit=20
   ```

---

## 🎯 Quick Commands

```bash
# Create new business type
npm run new-business -- --name=restaurant

# Create new role dashboard
npm run new-role -- --business=clinic --role=nurse

# Test messaging
npm run test:messages

# Build for production
npm run build

# Deploy
npm run deploy
```

---

**Happy Coding! 🚀**
