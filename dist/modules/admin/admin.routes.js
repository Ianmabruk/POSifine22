import { Router } from 'express';
const router = Router();
router.get('/admin', (req, res) => {
    res.json({ message: 'Admin Dashboard' });
});
router.get('/cashier', (req, res) => {
    res.json({ message: 'Cashier Dashboard' });
});
router.get('/broadcast', (req, res) => {
    res.json({ message: 'Broadcast Page' });
});
export default router;
