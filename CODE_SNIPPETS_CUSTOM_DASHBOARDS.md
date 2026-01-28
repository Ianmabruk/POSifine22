# Code Snippets for Custom Dashboard System

## Frontend Integration Examples

### 1. Business Type Selector Component Usage

```jsx
// In your App.jsx or routing file
import BusinessTypeSelector from './pages/BusinessTypeSelector';

<Route 
  path="/select-business-type" 
  element={
    <ProtectedRoute adminOnly>
      <BusinessTypeSelector />
    </ProtectedRoute>
  } 
/>
```

### 2. Business API Service Functions

```javascript
// Add to my-react-app/src/services/api.js

export const business = {
  /**
   * Get all available business types
   */
  async getBusinessTypes() {
    try {
      const response = await fetch(`${BASE_API_URL}/business/business-types`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (!response.ok) throw new Error('Failed to fetch business types');
      return await response.json();
    } catch (error) {
      console.error('Error fetching business types:', error);
      throw error;
    }
  },

  /**
   * Select business type for current admin
   */
  async selectBusinessType(businessType, settings = {}) {
    try {
      const response = await fetch(`${BASE_API_URL}/business/select`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ 
          business_type: businessType,
          settings 
        })
      });
      if (!response.ok) throw new Error('Failed to select business type');
      return await response.json();
    } catch (error) {
      console.error('Error selecting business type:', error);
      throw error;
    }
  },

  /**
   * Get current business profile
   */
  async getBusinessProfile() {
    try {
      const response = await fetch(`${BASE_API_URL}/business/profile`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (!response.ok) throw new Error('Failed to fetch business profile');
      return await response.json();
    } catch (error) {
      console.error('Error fetching business profile:', error);
      throw error;
    }
  },

  /**
   * Get available roles for a business type
   */
  async getBusinessRoles(businessType) {
    try {
      const response = await fetch(`${BASE_API_URL}/business/business-types/${businessType}/roles`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (!response.ok) throw new Error('Failed to fetch business roles');
      return await response.json();
    } catch (error) {
      console.error('Error fetching business roles:', error);
      throw error;
    }
  },

  /**
   * Create a new business user
   */
  async createBusinessUser(userData) {
    try {
      const response = await fetch(`${BASE_API_URL}/business/users`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(userData)
      });
      if (!response.ok) throw new Error('Failed to create business user');
      return await response.json();
    } catch (error) {
      console.error('Error creating business user:', error);
      throw error;
    }
  },

  /**
   * Get all users in current business
   */
  async getBusinessUsers() {
    try {
      const response = await fetch(`${BASE_API_URL}/business/users`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (!response.ok) throw new Error('Failed to fetch business users');
      return await response.json();
    } catch (error) {
      console.error('Error fetching business users:', error);
      throw error;
    }
  },

  /**
   * Update business user
   */
  async updateBusinessUser(userId, updates) {
    try {
      const response = await fetch(`${BASE_API_URL}/business/users/${userId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(updates)
      });
      if (!response.ok) throw new Error('Failed to update business user');
      return await response.json();
    } catch (error) {
      console.error('Error updating business user:', error);
      throw error;
    }
  },

  /**
   * Delete business user
   */
  async deleteBusinessUser(userId) {
    try {
      const response = await fetch(`${BASE_API_URL}/business/users/${userId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (!response.ok) throw new Error('Failed to delete business user');
      return await response.json();
    } catch (error) {
      console.error('Error deleting business user:', error);
      throw error;
    }
  }
};
```

### 3. Business User Management Component

```jsx
// Create: my-react-app/src/components/BusinessUserForm.jsx

import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { business } from '../services/api';
import { Plus, X } from 'lucide-react';

export default function BusinessUserForm({ onUserCreated, onCancel }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [roles, setRoles] = useState([]);
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    business_role: '',
    hourly_rate: 0
  });

  useEffect(() => {
    loadRoles();
  }, []);

  const loadRoles = async () => {
    try {
      const businessType = user?.businessType || user?.business_type;
      if (!businessType) return;

      const response = await business.getBusinessRoles(businessType);
      if (response.success) {
        setRoles(response.roles);
        // Set default role
        if (response.roles.length > 0) {
          setFormData(prev => ({ ...prev, business_role: response.roles[0].id }));
        }
      }
    } catch (error) {
      console.error('Error loading roles:', error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await business.createBusinessUser(formData);
      if (response.success) {
        alert(`User created successfully!\nEmail: ${formData.email}\nDefault Password: ${response.defaultPassword}`);
        onUserCreated(response.user);
        setFormData({
          name: '',
          email: '',
          password: '',
          business_role: roles[0]?.id || '',
          hourly_rate: 0
        });
      } else {
        setError(response.error || 'Failed to create user');
      }
    } catch (error) {
      setError(error.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Add Business User</h2>
        <button onClick={onCancel} className="text-gray-400 hover:text-gray-600">
          <X className="w-6 h-6" />
        </button>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Full Name *
          </label>
          <input
            type="text"
            required
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Enter full name"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Email Address *
          </label>
          <input
            type="email"
            required
            value={formData.email}
            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="user@example.com"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Password *
          </label>
          <input
            type="password"
            required
            value={formData.password}
            onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Enter password"
          />
          <p className="mt-1 text-xs text-gray-500">Minimum 6 characters</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Role *
          </label>
          <select
            required
            value={formData.business_role}
            onChange={(e) => setFormData({ ...formData, business_role: e.target.value })}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            {roles.map(role => (
              <option key={role.id} value={role.id}>
                {role.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Hourly Rate (Optional)
          </label>
          <input
            type="number"
            step="0.01"
            value={formData.hourly_rate}
            onChange={(e) => setFormData({ ...formData, hourly_rate: parseFloat(e.target.value) || 0 })}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="0.00"
          />
        </div>

        <div className="flex gap-3 pt-4">
          <button
            type="submit"
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-700 hover:to-purple-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
          >
            {loading ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                <span>Creating...</span>
              </>
            ) : (
              <>
                <Plus className="w-5 h-5" />
                <span>Create User</span>
              </>
            )}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
```

### 4. Using Business User Form in Dashboard

```jsx
// In any Business Dashboard component (e.g., SupermarketDashboard.jsx)

import React, { useState } from 'react';
import BusinessUserForm from '../../components/BusinessUserForm';

export default function SupermarketDashboard() {
  const [showUserForm, setShowUserForm] = useState(false);
  const [users, setUsers] = useState([]);

  const handleUserCreated = (newUser) => {
    setUsers([...users, newUser]);
    setShowUserForm(false);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ... header ... */}
      
      {/* User Management Section */}
      {activeTab === 'users' && (
        <div>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold text-gray-900">User Management</h2>
            <button
              onClick={() => setShowUserForm(true)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              <Plus className="w-4 h-4" />
              Add User
            </button>
          </div>

          {showUserForm ? (
            <BusinessUserForm
              onUserCreated={handleUserCreated}
              onCancel={() => setShowUserForm(false)}
            />
          ) : (
            <div className="bg-white rounded-lg shadow">
              {/* User list here */}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

### 5. Enhanced Auth.jsx Login Redirection

```jsx
// Update handleSubmit in my-react-app/src/pages/Auth.jsx

const handleSubmit = async (e) => {
  e.preventDefault();
  // ... existing code ...

  // After successful login
  if (res.token && res.user) {
    await login(res);
    
    // ENHANCED REDIRECTION LOGIC
    const user = res.user;
    
    // Owner/Super Admin
    if (user.role === 'owner') {
      navigate('/main-admin');
      return;
    }
    
    // Pro Plan with Business Type
    if (user.plan === 'pro' && (user.businessType || user.business_type)) {
      navigate('/pro-dashboard');
      return;
    }
    
    // Pro Plan Admin without Business Type
    if (user.plan === 'pro' && user.role === 'admin' && !user.businessType && !user.business_type) {
      navigate('/select-business-type');
      return;
    }
    
    // Basic/Ultra Admin
    if (user.role === 'admin') {
      navigate('/admin');
      return;
    }
    
    // Cashier/Regular User
    if (user.role === 'cashier') {
      navigate('/cashier');
      return;
    }
    
    // Fallback
    navigate('/dashboard');
  }
};
```

### 6. Backend: Adding Custom Business Logic

```python
# In backend/app.py or a custom business controller

@app.route('/api/clinic/patients', methods=['GET'])
@auth.require_auth
def get_clinic_patients():
    """Get all patients for clinic business"""
    try:
        user = request.user
        account_id = user.get('account_id')
        
        # Verify user is in clinic business
        business_type = user.get('business_type')
        if business_type != 'clinic':
            return jsonify({'error': 'This endpoint is only for clinic businesses'}), 403
        
        # Get patients for this clinic
        patients = datastore.find('patients', {'account_id': account_id})
        
        return jsonify({
            'success': True,
            'patients': patients
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching clinic patients: {e}")
        return jsonify({'error': str(e)}), 500
```

## Backend Implementation Examples

### 1. Adding Custom Permissions Check

```python
# In backend/business_routes.py

def check_permission(user, required_permission):
    """Check if user has required permission for their role"""
    from business_types import get_roles_for_business_type
    
    business_type = user.get('business_type')
    business_role = user.get('business_role')
    
    if not business_type or not business_role:
        return False
    
    roles = get_roles_for_business_type(business_type)
    user_role = next((r for r in roles if r['id'] == business_role), None)
    
    if not user_role:
        return False
    
    return required_permission in user_role.get('permissions', [])

# Usage in route
@business_bp.route('/clinic/prescribe', methods=['POST'])
@auth_controller.require_auth
def prescribe_medication():
    user = request.user
    
    if not check_permission(user, 'prescribe'):
        return jsonify({'error': 'You do not have permission to prescribe'}), 403
    
    # ... prescribe logic ...
```

### 2. Custom Business Data Models

```python
# Add to backend/models.py

@dataclass
class ClinicPatient:
    """Patient record for clinic business"""
    id: str
    account_id: str
    patient_number: str
    name: str
    date_of_birth: str
    gender: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    medical_history: List[Dict] = field(default_factory=list)
    prescriptions: List[Dict] = field(default_factory=list)
    appointments: List[Dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)
```

## Testing Examples

### 1. Testing Business Type Selection

```javascript
// Test in browser console or as part of test suite

async function testBusinessTypeSelection() {
  // 1. Get business types
  const types = await business.getBusinessTypes();
  console.log('Available business types:', types);
  
  // 2. Select a business type
  const result = await business.selectBusinessType('clinic');
  console.log('Selection result:', result);
  
  // 3. Verify profile was created
  const profile = await business.getBusinessProfile();
  console.log('Business profile:', profile);
  
  // All should succeed if user is Pro admin
}
```

### 2. Testing User Creation

```javascript
async function testUserCreation() {
  // Create a doctor user for clinic
  const userData = {
    name: 'Dr. Test User',
    email: 'doctor.test@clinic.com',
    password: 'testpass123',
    business_role: 'doctor',
    hourly_rate: 500.00
  };
  
  try {
    const result = await business.createBusinessUser(userData);
    console.log('User created:', result);
    
    // Verify user appears in list
    const users = await business.getBusinessUsers();
    console.log('All users:', users);
    
    console.log('✅ User creation test passed');
  } catch (error) {
    console.error('❌ User creation test failed:', error);
  }
}
```

## Deployment Checklist

- [ ] Backend: Ensure `business_types.py` is in backend folder
- [ ] Backend: Ensure `business_routes.py` is in backend folder
- [ ] Backend: Verify routes are registered in `app.py`
- [ ] Backend: Run database migration if using PostgreSQL
- [ ] Frontend: Add business API functions to `api.js`
- [ ] Frontend: Create `BusinessUserForm.jsx` component
- [ ] Frontend: Update `App.jsx` with new routes
- [ ] Frontend: Test all dashboards render correctly
- [ ] Test Pro signup flow end-to-end
- [ ] Test Basic/Ultra plans still work
- [ ] Deploy backend changes
- [ ] Deploy frontend changes
- [ ] Verify in production environment
