export const requireUltra = (req, res, next) => {
    if (req.user?.plan !== "ultra") {
        return res.status(403).json({
            success: false,
            error: "Ultra subscription required"
        });
    }
    next();
};
export const requireAdmin = (req, res, next) => {
    if (req.user?.role !== "admin") {
        return res.status(403).json({
            success: false,
            error: "Admin access only"
        });
    }
    next();
};
