export const requireUltra = (req, res, next) => {
    if (req.user?.plan !== "business") {
        return res.status(403).json({
            success: false,
            error: "Ultra subscription required"
        });
    }
    next();
};
export const requireAdmin = (req, res, next) => {
    if (req.user?.role !== "admin" && req.user?.role !== "main_admin") {
        return res.status(403).json({
            success: false,
            error: "Admin access only"
        });
    }
    next();
};
export const requireSuperAdmin = (req, res, next) => {
    if (req.user?.role !== "main_admin") {
        return res.status(403).json({
            success: false,
            error: "Super Admin access required"
        });
    }
    next();
};
