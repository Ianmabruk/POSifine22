import { ProductsRepo } from "./products.repository";

export const ProductsService = {
  list: () => ProductsRepo.list(),
  get: (id: string) => ProductsRepo.get(id),
  create: (data: any) => ProductsRepo.create(data),
  update: (id: string, data: any) => ProductsRepo.update(id, data)
};
