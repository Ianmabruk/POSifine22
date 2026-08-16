import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { useHistory } from 'react-router-dom';
const BroadcastPage = () => {
    const [role, setRole] = useState('');
    const [eventType, setEventType] = useState('');
    const [data, setData] = useState('');
    const [message, setMessage] = useState('');
    const history = useHistory();
    const handleSubmit = async (e) => {
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
        }
        catch (error) {
            setMessage('Error: ' + error.message);
        }
    };
    const handleRoleChange = (e) => {
        setRole(e.target.value);
    };
    const handleEventChange = (e) => {
        setEventType(e.target.value);
    };
    return (_jsx("div", { className: "min-h-screen bg-gray-50", children: _jsxs("div", { className: "container mx-auto px-4 py-8", children: [_jsxs("div", { className: "flex justify-between items-center mb-6", children: [_jsx("h1", { className: "text-3xl font-bold text-blue-600", children: "Broadcast Events" }), _jsxs("nav", { className: "flex space-x-4", children: [_jsx("a", { href: "#/admin", className: "text-gray-600 hover:text-blue-500", children: "Admin Dashboard" }), _jsx("a", { href: "#/cashier", className: "text-gray-600 hover:text-blue-500", children: "Cashier Dashboard" }), _jsx("a", { href: "#/broadcast", className: "text-gray-600 hover:text-blue-500", children: "Broadcast" })] })] }), _jsxs("div", { className: "bg-white rounded-lg shadow-md p-6", children: [_jsx("h2", { className: "text-xl font-semibold text-gray-800 mb-4", children: "Broadcast Message" }), _jsxs("form", { onSubmit: handleSubmit, className: "space-y-4", children: [_jsxs("div", { className: "flex items-center mb-4", children: [_jsx("label", { className: "w-20 flex flex-col justify-center", children: _jsx("span", { className: "text-sm font-medium text-gray-700", children: "Role" }) }), _jsxs("select", { value: role, onChange: (e) => setRole(e.target.value), className: "flex-1 p-2 border rounded", children: [_jsx("option", { value: "", children: "Select Role" }), _jsx("option", { value: "admin", children: "Admin" }), _jsx("option", { value: "cashier", children: "Cashier" }), _jsx("option", { value: "main_admin", children: "Main Admin" })] })] }), _jsxs("div", { className: "flex items-center mb-4", children: [_jsx("label", { className: "w-20 flex flex-col justify-center", children: _jsx("span", { className: "text-sm font-medium text-gray-700", children: "Event" }) }), _jsxs("select", { value: eventType, onChange: (e) => setEventType(e.target.value), className: "flex-1 p-2 border rounded", children: [_jsx("option", { value: "", children: "Select Event" }), _jsx("option", { value: "ORDER_CREATED", children: "New Order Created" }), _jsx("option", { value: "USER_REGISTERED", children: "User Registered" }), _jsx("option", { value: "PAYMENT_APPROVED", children: "Payment Approved" }), _jsx("option", { value: "TRIAL_EXTENDED", children: "Trial Extended" }), _jsx("option", { value: "ACCOUNT_LOCKED", children: "Account Locked" }), _jsx("option", { value: "ACCOUNT_UNLOCKED", children: "Account Unlocked" })] })] }), _jsxs("div", { className: "flex items-center mb-4", children: [_jsx("label", { className: "w-20 flex flex-col justify-center", children: _jsx("span", { className: "text-sm font-medium text-gray-700", children: "Data" }) }), _jsx("textarea", { value: data, onChange: (e) => setData(e.target.value), rows: 3, className: "flex-1 p-2 border rounded w-full" })] }), _jsxs("div", { className: "flex justify-between", children: [_jsx("button", { type: "submit", className: "bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700", children: "Broadcast" }), _jsx("button", { type: "button", onClick: () => history.push('/admin'), className: "text-gray-600 hover:text-blue-500", children: "Back to Admin Dashboard" })] })] }), message && _jsx("p", { className: "text-sm text-gray-600 mt-4", children: message })] })] }) }));
};
export default BroadcastPage;
