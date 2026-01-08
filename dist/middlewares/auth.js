import jwt from "jsonwebtoken";
export const verifyToken = (req, res, next) => {
    const token = req.headers.authorization?.split(" ")[1];
    if (!token) {
        return res.status(401).json({ error: "No token provided" });
    }
    try {
        const secret = process.env.JWT_SECRET;
        if (!secret) {
            return res.status(500).json({ error: "Server misconfigured: JWT_SECRET missing" });
        }
        const decoded = jwt.verify(token, secret);
        req.user = decoded;
        next();
    }
    catch {
        return res.status(401).json({ error: "Invalid token" });
    }
};
// Backwards-compatible exports expected by routes
export const authenticateJWT = verifyToken;
export const authorize = (roles) => (req, res, next) => {
    const userRole = req.user?.role?.toUpperCase();
    if (!userRole || !roles.map((r) => r.toUpperCase()).includes(userRole)) {
        return res.status(403).json({ error: "Forbidden" });
    }
    next();
};
