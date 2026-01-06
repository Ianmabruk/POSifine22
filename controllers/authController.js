import User from "../models/User.js";
import jwt from "jsonwebtoken";

// Signup
export const signup = async (req, res) => {
  try {
    const { name, email, password, plan = "basic" } = req.body;

    if (!name || !email || !password) {
      return res.status(400).json({ error: "Name, email, and password are required" });
    }

    const existing = await User.findOne({ email: email.toLowerCase() });
    if (existing) return res.status(400).json({ error: "User already exists" });

    const role = (plan === "ultra") ? "admin" : "cashier";

    const user = await User.create({ 
      name, 
      email: email.toLowerCase(), 
      password, 
      plan, 
      package: plan,
      role 
    });

    const token = jwt.sign(
      { 
        id: user._id, 
        role: user.role, 
        plan: user.plan,
        package: user.package,
        accountId: user.accountId 
      },
      process.env.JWT_SECRET,
      { expiresIn: "7d" }
    );

    res.status(201).json({ 
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
    });

  } catch (err) {
    console.error("Signup error:", err);
    res.status(500).json({ error: "Signup failed" });
  }
};

// Login
export const login = async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: "Email and password are required" });
    }

    const user = await User.findOne({ email: email.toLowerCase() });
    if (!user) return res.status(401).json({ error: "Invalid credentials" });

    const match = await user.comparePassword(password);
    if (!match) return res.status(401).json({ error: "Invalid credentials" });

    const token = jwt.sign(
      { 
        id: user._id, 
        role: user.role, 
        plan: user.plan,
        package: user.package,
        accountId: user.accountId 
      },
      process.env.JWT_SECRET,
      { expiresIn: "7d" }
    );

    res.status(200).json({ 
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
    });

  } catch (err) {
    console.error("Login error:", err);
    res.status(500).json({ error: "Login failed" });
  }
};

// PIN Login
export const pinLogin = async (req, res) => {
  try {
    const { email, pin } = req.body;

    if (!email || !pin || pin.length !== 4) {
      return res.status(400).json({ error: "Email and 4-digit PIN are required" });
    }

    const user = await User.findOne({ email: email.toLowerCase() });
    if (!user || !user.pin || user.pin !== pin) {
      return res.status(401).json({ error: "Invalid PIN" });
    }

    const token = jwt.sign(
      { 
        id: user._id, 
        role: user.role, 
        plan: user.plan,
        package: user.package,
        accountId: user.accountId 
      },
      process.env.JWT_SECRET,
      { expiresIn: "7d" }
    );

    res.status(200).json({ 
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
    });

  } catch (err) {
    console.error("PIN login error:", err);
    res.status(500).json({ error: "PIN login failed" });
  }
};