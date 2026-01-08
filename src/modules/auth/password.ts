import bcrypt from "bcrypt";
import { env } from "../../config/env";

export async function hashPassword(pw: string) {
  const saltRounds = env.BCRYPT_ROUNDS;
  return bcrypt.hash(pw, saltRounds);
}

export async function comparePassword(pw: string, hash: string) {
  return bcrypt.compare(pw, hash);
}
