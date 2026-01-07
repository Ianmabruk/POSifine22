import User from "../models/User.js";
import jwt from "jsonwebtoken";

// Signup
export const signup = async (req, res) => {
  try {
    const { name, email, password, plan = "basic" } = req.body || {};

    // Basic validation
    if (!name || !email || !password) {
      return res.status(400).json({ success: false, error: { code: "VALIDATION_ERROR", message: "Name, email, and password are required" } });
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      return res.status(400).json({ success: false, error: { code: "INVALID_EMAIL", message: "Email format is invalid" } });
    }
    if (password.length < 6) {
      return res.status(400).json({ success: false, error: { code: "WEAK_PASSWORD", message: "Password must be at least 6 characters" } });
    }

    // Check duplicate
    const existing = await User.findOne({ email: email.toLowerCase() });
    if (existing) {
      return res.status(409).json({ success: false, error: { code: "EMAIL_TAKEN", message: "Email already registered" } });
    }

    const role = plan === "ultra" ? "admin" : "cashier";

    // Create user
    const user = await User.create({
      name,
      email: email.toLowerCase(),
      password,
      plan,
      package: plan,
      role
    });

    const secret = process.env.JWT_SECRET;
    if (!secret) {
      return res.status(500).json({ success: false, error: { code: "SERVER_MISCONFIG", message: "JWT secret not configured" } });
    }

    const token = jwt.sign(
      {
        id: user._id,
        role: user.role,
        plan: user.plan,
        package: user.package,
        accountId: user.accountId
      },
      secret,
      { expiresIn: "7d" }
    );

    return res.status(201).json({
      success: true,
      data: {
        token,
        user: {
          id: user._id,
          name: user.name,
          email: user.email,
          role: user.role,
          plan: user.plan,
          accountId: user.accountId,
          active: user.active
        }
      }
    });
  } catch (err) {
    console.error("Signup error:", err);
    // Handle Mongo duplicate key error fallback
    if (err && err.code === 11000) {
      return res.status(409).json({ success: false, error: { code: "EMAIL_TAKEN", message: "Email already registered" } });
    }
    return res.status(500).json({ success: false, error: { code: "INTERNAL_SERVER_ERROR", message: "Signup failed" } });
  }
};

// Login
export const login = async (req, res) => {
  try {
    const { email, password } = req.body || {};

    if (!email || !password) {
      return res.status(400).json({ success: false, error: { code: "VALIDATION_ERROR", message: "Email and password are required" } });
    }

    const user = await User.findOne({ email: email.toLowerCase() });
    if (!user) return res.status(401).json({ success: false, error: { code: "INVALID_CREDENTIALS", message: "Invalid credentials" } });

    const match = await user.comparePassword(password);
    if (!match) return res.status(401).json({ success: false, error: { code: "INVALID_CREDENTIALS", message: "Invalid credentials" } });

    const secret = process.env.JWT_SECRET;
    if (!secret) {
      return res.status(500).json({ success: false, error: { code: "SERVER_MISCONFIG", message: "JWT secret not configured" } });
    }

    const token = jwt.sign(
      {
        id: user._id,
        role: user.role,
        plan: user.plan,
        package: user.package,
        accountId: user.accountId
      },
      secret,
      { expiresIn: "7d" }
    );

    return res.status(200).json({
      success: true,
      data: {
        token,
        user: {
          id: user._id,
          name: user.name,
          email: user.email,
          role: user.role,
          plan: user.plan,
          accountId: user.accountId,
          active: user.active
        }
      }
    });
  } catch (err) {
    console.error("Login error:", err);
    return res.status(500).json({ success: false, error: { code: "INTERNAL_SERVER_ERROR", message: "Login failed" } });
  }
};

// PIN Login
export const pinLogin = async (req, res) => {
  try {
    const { email, pin } = req.body || {};

    if (!email || !pin || String(pin).length !== 4) {
      return res.status(400).json({ success: false, error: { code: "VALIDATION_ERROR", message: "Email and 4-digit PIN are required" } });
    }

    const user = await User.findOne({ email: email.toLowerCase() });
    if (!user || !user.pin || user.pin !== pin) {
      return res.status(401).json({ success: false, error: { code: "INVALID_PIN", message: "Invalid PIN" } });
    }

    const secret = process.env.JWT_SECRET;
    if (!secret) {
      return res.status(500).json({ success: false, error: { code: "SERVER_MISCONFIG", message: "JWT secret not configured" } });
    }

    const token = jwt.sign(
      {
        id: user._id,
        role: user.role,
        plan: user.plan,
        package: user.package,
        accountId: user.accountId
      },
      secret,
      { expiresIn: "7d" }
    );

    return res.status(200).json({
      success: true,
      data: {
        token,
        user: {
          id: user._id,
          name: user.name,
          email: user.email,
          role: user.role,
          plan: user.plan,
          accountId: user.accountId,
          active: user.active
        }
      }
    });
  } catch (err) {
    console.error("PIN login error:", err);
    return res.status(500).json({ success: false, error: { code: "INTERNAL_SERVER_ERROR", message: "PIN login failed" } });
  }
};