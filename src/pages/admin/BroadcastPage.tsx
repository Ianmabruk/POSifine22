import React, { useState } from 'react';
import { useHistory } from 'react-router-dom';

const BroadcastPage = () => {
  const [role, setRole] = useState('');
  const [eventType, setEventType] = useState('');
  const [data, setData] = useState('');
  const [message, setMessage] = useState('');
  const history = useHistory();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!role || !eventType || !data) {
      setMessage('All fields are required');
      return;
    }
    
    try {
      const parsedData = JSON.parse(data);
      const response = await fetch('/api/v1/main-admin/broadcast', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ role, event: eventType, data: parsedData }),
      });
      const result = await response.json();
      setMessage(result.message);
      if (result.success) {
        setRole('');
        setEventType('');
        setData('');
      }
    } catch (error) {
      setMessage('Error: ' + (error as Error).message);
    }
  };

  const handleRoleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setRole(e.target.value);
  };

  const handleEventChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setEventType(e.target.value);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="container mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold text-blue-600">Broadcast Events</h1>
          <nav className="flex space-x-4">
            <a href="#/admin" className="text-gray-600 hover:text-blue-500">Admin Dashboard</a>
            <a href="#/cashier" className="text-gray-600 hover:text-blue-500">Cashier Dashboard</a>
            <a href="#/broadcast" className="text-gray-600 hover:text-blue-500">Broadcast</a>
          </nav>
        </div>

        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold text-gray-800 mb-4">Broadcast Message</h2>
          
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex items-center mb-4">
              <label className="w-20 flex flex-col justify-center">
                <span className="text-sm font-medium text-gray-700">Role</span>
              </label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="flex-1 p-2 border rounded"
              >
                <option value="">Select Role</option>
                <option value="admin">Admin</option>
                <option value="cashier">Cashier</option>
                <option value="main_admin">Main Admin</option>
              </select>
            </div>

            <div className="flex items-center mb-4">
              <label className="w-20 flex flex-col justify-center">
                <span className="text-sm font-medium text-gray-700">Event</span>
              </label>
              <select
                value={eventType}
                onChange={(e) => setEventType(e.target.value)}
                className="flex-1 p-2 border rounded"
              >
                <option value="">Select Event</option>
                <option value="ORDER_CREATED">New Order Created</option>
                <option value="USER_REGISTERED">User Registered</option>
                <option value="PAYMENT_APPROVED">Payment Approved</option>
                <option value="TRIAL_EXTENDED">Trial Extended</option>
                <option value="ACCOUNT_LOCKED">Account Locked</option>
                <option value="ACCOUNT_UNLOCKED">Account Unlocked</option>
              </select>
            </div>

            <div className="flex items-center mb-4">
              <label className="w-20 flex flex-col justify-center">
                <span className="text-sm font-medium text-gray-700">Data</span>
              </label>
              <textarea
                value={data}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setData(e.target.value)}
                rows={3}
                className="flex-1 p-2 border rounded w-full"
              />
            </div>

            <div className="flex justify-between">
              <button
                type="submit"
                className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
              >
                Broadcast
              </button>
              <button
                type="button"
                onClick={() => history.push('/admin')}
                className="text-gray-600 hover:text-blue-500"
              >
                Back to Admin Dashboard
              </button>
            </div>
          </form>
          
          {message && <p className="text-sm text-gray-600 mt-4">{message}</p>}
        </div>
      </div>
    </div>
  );
};

export default BroadcastPage;

