import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
const AdminDashboard = () => {
    const [messages, setMessages] = useState([]);
    const [role, setRole] = useState('');
    const navigate = useNavigate();
    useEffect(() => {
        // Check if socket.io is available
        if (typeof window !== 'undefined' && !window.io) {
            console.error('Socket.io not available');
            return;
        }
        // Connect to socket
        const socket = window.io('/socket.io');
        // Set role
        setRole('admin'); // In a real app, this would be determined by auth
        // Join role room
        socket.emit('join', { role });
        // Listen for events
        socket.on('broadcast', (eventData) => {
            setMessages(prev => [...prev, { type: eventData.type, role: eventData.role, data: eventData.data }]);
        });
        // Cleanup on unmount
        return () => {
            socket.disconnect();
        };
    }, []);
    const handleBroadcast = (role, event, data) => {
        // In a real admin dashboard, we'd have a way to trigger broadcasts
        // For now, we'll simulate some common events
        const eventTypes = {
            'ORDER_CREATED': 'New order created',
            'USER_REGISTERED': 'User registered',
            'PAYMENT_APPROVED': 'Payment approved',
            'TRIAL_EXTENDED': 'Trial extended',
            'ACCOUNT_LOCKED': 'Account locked',
            'ACCOUNT_UNLOCKED': 'Account unlocked'
        };
        const event = {
            type: event,
            role,
            data
        };
        // Simulate broadcasting
        setMessages(prev => [...prev, { ...event }]);
    };
    return (<div className="min-h-screen bg-gray-50">
      <div className="container mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold text-blue-600">Admin Dashboard</h1>
          <nav className="flex space-x-4">
            <a href="#orders" className="text-gray-600 hover:text-blue-500">Orders</a>
            <a href="#users" className="text-gray-600 hover:text-blue-500">Users</a>
            <a href="#payments" className="text-gray-600 hover:text-blue-500">Payments</a>
            <a href="#trials" className="text-gray-600 hover:text-blue-500">Trials</a>
          </nav>
        </div>

        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold text-gray-800 mb-4">Real-time Events</h2>
          
          {messages.length === 0 ? (<p className="text-gray-500 text-center">No events yet. Connecting to real-time feed...</p>) : (<div className="max-h-96 overflow-y-auto space-y-2">
              {messages.map((msg, index) => (<div key={index} className="p-3 bg-gray-50 rounded">
                  <div className="flex items-center">
                    <span className="text-xs font-semibold text-gray-500 mr-2">
                      {new Date().toLocaleTimeString()}: 
                    </span>
                    <span className="font-medium">{msg.role}:</span>
                    <span className="text-blue-500">{msg.type}</span>
                  </div>
                  <div className="text-sm text-gray-600 mt-1">{msg.data}</div>
                </div>))}
          </div>)}
        </div>

        <div className="mt-8">
          <h3 className="text-lg font-semibold text-gray-800">Broadcast Message</h3>
          <form onSubmit={(e) => handleSubmit(e)}>
            <div className="flex space-x-2">
              <input type="text" placeholder="Role (admin/cashier/main_admin)" value={role} onChange={(e) => setRole(e.target.value)} className="flex-1 p-2 border rounded"/>
              <input type="text" placeholder="Event (e.g., ORDER_CREATED)" value={eventType || ''} onChange={(e) => setEventType(e.target.value)} className="flex-1 p-2 border rounded"/>
              <input type="text" placeholder="Data (JSON string)" value={data || ''} onChange={(e) => setData(e.target.value)} className="flex-1 p-2 border rounded"/>
              <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
                Broadcast
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>);
};
export default AdminDashboard;
