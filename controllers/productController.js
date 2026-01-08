import Product from "../models/Product.js";
import { getIO } from "../socket.js";

/**
 * GET PRODUCTS (Admin + Cashier)
 */
export const getProducts = async (req, res) => {
  try {
    const products = await Product.find({
      accountId: req.user.accountId
    }).sort({ createdAt: -1 });

    res.json({ success: true, data: products });
  } catch (err) {
    res.status(500).json({ error: "Failed to fetch products" });
  }
};

/**
 * CREATE PRODUCT (ADMIN ONLY)
 */
export const createProduct = async (req, res) => {
  try {
    const {
      name,
      price,
      cost = 0,
      quantity = 0,
      image = "",
      category = "general",
      unit = "pcs",
      recipe = []
    } = req.body;

    if (!name || price == null) {
      return res.status(400).json({ error: "Name and price required" });
    }

    const product = await Product.create({
      name,
      price,
      cost,
      quantity,
      image,
      category,
      unit,
      recipe,
      isComposite: recipe.length > 0,
      accountId: req.user.accountId,
      createdBy: req.user.id
    });

    // 🔥 REAL-TIME PUSH
    getIO().to(req.user.accountId).emit("productCreated", product);

    res.status(201).json({ success: true, data: product });
  } catch (err) {
    res.status(500).json({ error: "Failed to create product" });
  }
};

/**
 * UPDATE PRODUCT (ADMIN ONLY)
 */
export const updateProduct = async (req, res) => {
  try {
    const updated = await Product.findOneAndUpdate(
      { _id: req.params.id, accountId: req.user.accountId },
      req.body,
      { new: true }
    );

    if (!updated) {
      return res.status(404).json({ error: "Product not found" });
    }

    // 🔥 REAL-TIME PUSH
    getIO().to(req.user.accountId).emit("productUpdated", updated);

    res.json({ success: true, data: updated });
  } catch (err) {
    res.status(500).json({ error: "Update failed" });
  }
};

/**
 * DELETE PRODUCT (ADMIN ONLY)
 */
export const deleteProduct = async (req, res) => {
  try {
    const deleted = await Product.findOneAndDelete({
      _id: req.params.id,
      accountId: req.user.accountId
    });

    if (!deleted) {
      return res.status(404).json({ error: "Product not found" });
    }

    // 🔥 REAL-TIME PUSH
    getIO().to(req.user.accountId).emit("productDeleted", deleted._id);

    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: "Delete failed" });
  }
};
