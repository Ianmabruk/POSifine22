import Product from "../models/Product.js";
import { verifyToken } from "./userController.js";

// Get all products
export const getProducts = async (req, res) => {
  try {
    const products = await Product.find({ accountId: req.user.accountId });
    res.json(products);
  } catch (err) {
    console.error("Get products error:", err);
    res.status(500).json({ error: "Failed to get products" });
  }
};

// Create product
export const createProduct = async (req, res) => {
  try {
    const { name, price, cost, quantity, image, category, unit, recipe } = req.body;

    if (!name || !price) {
      return res.status(400).json({ error: 'Name and price are required' });
    }

    const product = await Product.create({
      name,
      price: parseFloat(price),
      cost: parseFloat(cost) || 0,
      quantity: parseInt(quantity) || 0,
      image: image || '',
      category: category || 'general',
      unit: unit || 'pcs',
      recipe: recipe || [],
      isComposite: Boolean(recipe && recipe.length > 0),
      accountId: req.user.accountId,
      createdBy: req.user.id
    });

    res.status(201).json(product);
  } catch (err) {
    console.error("Create product error:", err);
    res.status(500).json({ error: "Failed to create product" });
  }
};

export { verifyToken };