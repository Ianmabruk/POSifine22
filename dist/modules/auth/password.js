import bcrypt from "bcrypt";
import { env } from "../../config/env";
export async function hashPassword(pw) {
    const saltRounds = env.BCRYPT_ROUNDS;
    return bcrypt.hash(pw, saltRounds);
}
export async function comparePassword(pw, hash) {
    return bcrypt.compare(pw, hash);
}
