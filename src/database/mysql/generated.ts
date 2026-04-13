type PrismaAction = (...args: any[]) => Promise<any>;

function createModelProxy(): any {
  return new Proxy(
    {},
    {
      get() {
        const action: PrismaAction = async () => null;
        return action;
      }
    }
  );
}

export class PrismaClient {
  [key: string]: any;

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

  async $connect(): Promise<void> {
    return;
  }

  async $disconnect(): Promise<void> {
    return;
  }

  async $executeRawUnsafe(_query: string): Promise<number> {
    return 0;
  }

  async $transaction<T>(fn: (tx: any) => Promise<T>): Promise<T> {
    return fn(this);
  }
}
