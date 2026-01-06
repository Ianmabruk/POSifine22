import express from "express";
import { getProducts, createProduct, verifyToken } from "../controllers/productController.js";

const router = express.Router();

router.get("/", verifyToken, getProducts);
router.post("/", verifyToken, createProduct);

export default router;