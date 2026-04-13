function createModelProxy() {
    return new Proxy({}, {
        get() {
            const action = async () => null;
            return action;
        }
    });
}
export class PrismaClient {
    constructor() {
        this.product = createModelProxy();
        this.syncQueue = createModelProxy();
        this.user = createModelProxy();
        this.session = createModelProxy();
        this.subscription = createModelProxy();
        this.sale = createModelProxy();
        this.saleItem = createModelProxy();
        this.activity = createModelProxy();
        this.deviceState = createModelProxy();
        this.priceHistory = createModelProxy();
    }
    async $connect() {
        return;
    }
    async $disconnect() {
        return;
    }
    async $executeRawUnsafe(_query) {
        return 0;
    }
    async $transaction(fn) {
        return fn(this);
    }
}
