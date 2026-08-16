import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
const AdminDashboard = () => {
    const [messages, setMessages] = useState([]);
    const [role, setRole] = useState('');
    const [eventType, setEventType] = useState('');
    const [data, setData] = useState('');
    useEffect(() => {
        if (typeof window !== 'undefined' && !window.io) {
            console.error('Socket.io not available');
            return;
        }
        const socket = window.io('/socket.io');
        setRole('admin');
        socket.emit('join', { role });
        socket.on('broadcast', (eventData) => {
            setMessages(prev => [...prev, { type: eventData.type, role: eventData.role, data: eventData.data }]);
        });
        return () => {
            socket.disconnect();
        };
    }, []);
    const handleSubmit = (e) => {
        e.preventDefault();
        setMessages(prev => [...prev, { type: eventType, role, data }]);
        setEventType('');
        setData('');
    };
    return (_jsx("div", { className: "min-h-screen bg-gray-50", children: _jsxs("div", { className: "container mx-auto px-4 py-8", children: [_jsxs("div", { className: "flex justify-between items-center mb-6", children: [_jsx("h1", { className: "text-3xl font-bold text-blue-600", children: "Admin Dashboard" }), _jsxs("nav", { className: "flex space-x-4", children: [_jsx("a", { href: "#orders", className: "text-gray-600 hover:text-blue-500", children: "Orders" }), _jsx("a", { href: "#users", className: "text-gray-600 hover:text-blue-500", children: "Users" }), _jsx("a", { href: "#payments", className: "text-gray-600 hover:text-blue-500", children: "Payments" }), _jsx("a", { href: "#trials", className: "text-gray-600 hover:text-blue-500", children: "Trials" })] })] }), _jsxs("div", { className: "bg-white rounded-lg shadow-md p-6", children: [_jsx("h2", { className: "text-xl font-semibold text-gray-800 mb-4", children: "Real-time Events" }), messages.length === 0 ? (_jsx("p", { className: "text-gray-500 text-center", children: "No events yet. Connecting to real-time feed..." })) : (_jsx("div", { className: "max-h-96 overflow-y-auto space-y-2", children: messages.map((msg, index) => (_jsxs("div", { className: "p-3 bg-gray-50 rounded", children: [_jsxs("div", { className: "flex items-center", children: [_jsxs("span", { className: "text-xs font-semibold text-gray-500 mr-2", children: [new Date().toLocaleTimeString(), ":"] }), _jsxs("span", { className: "font-medium", children: [msg.role, ":"] }), _jsx("span", { className: "text-blue-500", children: msg.type })] }), _jsx("div", { className: "text-sm text-gray-600 mt-1", children: String(msg.data) })] }, index))) }))] }), _jsxs("div", { className: "mt-8", children: [_jsx("h3", { className: "text-lg font-semibold text-gray-800", children: "Broadcast Message" }), _jsx("form", { onSubmit: handleSubmit, children: _jsxs("div", { className: "flex space-x-2", children: [_jsx("input", { type: "text", placeholder: "Role (admin/cashier/main_admin)", value: role, onChange: (e) => setRole(e.target.value), className: "flex-1 p-2 border rounded" }), _jsx("input", { type: "text", placeholder: "Event (e.g., ORDER_CREATED)", value: eventType, onChange: (e) => setEventType(e.target.value), className: "flex-1 p-2 border rounded" }), _jsx("input", { type: "text", placeholder: "Data (JSON string)", value: data, onChange: (e) => setData(e.target.value), className: "flex-1 p-2 border rounded w-full" }), _jsx("button", { type: "submit", className: "bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700", children: "Broadcast" })] }) })] })] }) }));
};
export default AdminDashboard;
