import User from "../models/User.js";
import jwt from "jsonwebtoken";
import bcrypt from "bcrypt";

// Utility function to generate JWT
const generateToken = (user) => {
  const secret = process.env.JWT_SECRET;
  if (!secret) throw new Error("JWT_SECRET not configured");

  return jwt.sign(
    {
      id: user._id,
      name: user.name,
      email: user.email,
      role: user.role,
      plan: user.plan,
      accountId: user.accountId || null,
    },
    secret,
    { expiresIn: "7d" }
  );
};

// ===== Signup =====
export const signup = async (req, res) => {
  try {
    const { name, email, password, plan = "basic" } = req.body || {};

    // Validation
    if (!name || !email || !password) {
      return res.status(400).json({ success: false, error: { code: "VALIDATION_ERROR", message: "Name, email, and password are required" } });
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      return res.status(400).json({ success: false, error: { code: "INVALID_EMAIL", message: "Email format is invalid" } });
    }
    if (password.length < 6) {
      return res.status(400).json({ success: false, error: { code: "WEAK_PASSWORD", message: "Password must be at least 6 characters" } });
    }

    // Check if email exists
    const existing = await User.findOne({ email: email.toLowerCase() });
    if (existing) return res.status(409).json({ success: false, error: { code: "EMAIL_TAKEN", message: "Email already registered" } });

    // Hash password
    const hashedPassword = await bcrypt.hash(password, 10);

    // Generate 4-digit PIN
    const pin = Math.floor(1000 + Math.random() * 9000);
    const hashedPin = await bcrypt.hash(pin.toString(), 10);

    // Assign role based on plan
    const role = plan === "ultra" ? "admin" : "cashier";

    // Create user
    const user = await User.create({
      name,
      email: email.toLowerCase(),
      password: hashedPassword,
      pin: hashedPin,
      plan,
      package: plan,
      role,
      active: true,
    });

    // Generate JWT
    const token = generateToken(user);

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
          accountId: user.accountId || null,
          active: user.active,
          pin, // optionally send PIN to display once or via email
        },
      },
    });
  } catch (err) {
    console.error("Signup error:", err);
    if (err.code === 11000) return res.status(409).json({ success: false, error: { code: "EMAIL_TAKEN", message: "Email already registered" } });
    return res.status(500).json({ success: false, error: { code: "INTERNAL_SERVER_ERROR", message: "Signup failed" } });
  }
};

// ===== Login =====
export const login = async (req, res) => {
  try {
    const { email, password } = req.body || {};

    if (!email || !password) {
      return res.status(400).json({ success: false, error: { code: "VALIDATION_ERROR", message: "Email and password are required" } });
    }

    const user = await User.findOne({ email: email.toLowerCase() });
    if (!user) return res.status(401).json({ success: false, error: { code: "INVALID_CREDENTIALS", message: "Invalid credentials" } });

    const match = await bcrypt.compare(password, user.password);
    if (!match) return res.status(401).json({ success: false, error: { code: "INVALID_CREDENTIALS", message: "Invalid credentials" } });

    const token = generateToken(user);

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
          accountId: user.accountId || null,
          active: user.active,
        },
      },
    });
  } catch (err) {
    console.error("Login error:", err);
    return res.status(500).json({ success: false, error: { code: "INTERNAL_SERVER_ERROR", message: "Login failed" } });
  }
};

// ===== PIN Login =====
export const pinLogin = async (req, res) => {
  try {
    const { email, pin } = req.body || {};

    if (!email || !pin || String(pin).length !== 4) {
      return res.status(400).json({ success: false, error: { code: "VALIDATION_ERROR", message: "Email and 4-digit PIN are required" } });
    }

    const user = await User.findOne({ email: email.toLowerCase() });
    if (!user || !user.pin) {
      return res.status(401).json({ success: false, error: { code: "INVALID_PIN", message: "Invalid PIN" } });
    }

    const matchPin = await bcrypt.compare(pin.toString(), user.pin);
    if (!matchPin) return res.status(401).json({ success: false, error: { code: "INVALID_PIN", message: "Invalid PIN" } });

    const token = generateToken(user);

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
          accountId: user.accountId || null,
          active: user.active,
        },
      },
    });
  } catch (err) {
    console.error("PIN login error:", err);
    return res.status(500).json({ success: false, error: { code: "INTERNAL_SERVER_ERROR", message: "PIN login failed" } });
  }
};
