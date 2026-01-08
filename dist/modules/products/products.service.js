import { ProductsRepo } from "./products.repository";
export const ProductsService = {
    list: () => ProductsRepo.list(),
    get: (id) => ProductsRepo.get(id),
    create: (data) => ProductsRepo.create(data),
    update: (id, data) => ProductsRepo.update(id, data)
};
