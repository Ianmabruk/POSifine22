import mongoose from "mongoose";

const productSchema = new mongoose.Schema({
  name: { type: String, required: true },
  price: { type: Number, required: true },
  cost: { type: Number, default: 0 },
  quantity: { type: Number, default: 0 },
  image: { type: String, default: "" },
  category: { type: String, default: "general" },
  unit: { type: String, default: "pcs" },
  recipe: { type: Array, default: [] },
  isComposite: { type: Boolean, default: false },
  accountId: { type: String, required: true },
  createdBy: { type: String }
}, { timestamps: true });

export default mongoose.model("Product", productSchema);