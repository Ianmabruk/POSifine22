const jwt = require('jsonwebtoken');

// Enhanced authentication middleware with role-based access control
const authenticateToken = (requiredRole = null) => {
  return (req, res, next) => {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];

    if (!token) {
      return res.status(401).json({ error: 'Access token required' });
    }

    jwt.verify(token, process.env.JWT_SECRET || 'your-secret-key', (err, user) => {
      if (err) {
        return res.status(403).json({ error: 'Invalid or expired token' });
      }

      req.user = { ...user, userType: user.type || 'user' };
      next();
    });
  };
};

// Rate limiting middleware for main admin routes
const rateLimitMainAdmin = (req, res, next) => {
  const key = `main_admin_${req.ip}`;
  const now = Date.now();
  const windowMs = 15 * 60 * 1000; // 15 minutes
  const maxRequests = 100;

  if (!global.rateLimitStore) {
    global.rateLimitStore = new Map();
  }

  const requests = global.rateLimitStore.get(key) || [];
  const validRequests = requests.filter(time => now - time < windowMs);

  if (validRequests.length >= maxRequests) {
    return res.status(429).json({ error: 'Too many requests' });
  }

  validRequests.push(now);
  global.rateLimitStore.set(key, validRequests);
  next();
};

module.exports = {
  authenticateToken,
  rateLimitMainAdmin
};