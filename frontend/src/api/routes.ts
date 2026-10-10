import { http } from "@/utils/http";

type Result = {
  success: boolean;
  data: unknown[];
};

export const getAsyncRoutes = () => {
  return http.request<Result>("get", "/get-async-routes");
};
