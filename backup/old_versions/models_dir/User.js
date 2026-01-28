import mongoose from "mongoose";
import bcrypt from "bcrypt";

const userSchema = new mongoose.Schema({
  name: { type: String, required: true },
  email: { type: String, required: true, unique: true },
  password: { type: String, required: true },
  role: { type: String, enum: ["admin", "cashier"], default: "cashier" },
  plan: { type: String, enum: ["basic", "ultra"], default: "basic" },
  package: { type: String, enum: ["basic", "ultra"], default: "basic" },
  accountId: { type: String, default: function() { return this._id.toString(); } },
  active: { type: Boolean, default: true },
  pin: { type: String },
  cashierPIN: { type: String }
}, { timestamps: true });

// Hash password before save
userSchema.pre("save", async function(next) {
  if (!this.isModified("password")) return next();
  const salt = await bcrypt.genSalt(10);
  this.password = await bcrypt.hash(this.password, salt);
  next();
});

userSchema.methods.comparePassword = async function(password) {
  return await bcrypt.compare(password, this.password);
};

export default mongoose.model("User", userSchema);