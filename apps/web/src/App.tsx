import { createBrowserRouter, Navigate, RouterProvider } from "react-router";
import { ChangePasswordPage } from "./features/auth/ChangePasswordPage";
import { LoginPage } from "./features/auth/LoginPage";
import { ProblemListPage } from "./features/practice/ProblemListPage";
import { ProblemPage } from "./features/practice/ProblemPage";
import { AppLayout, RequireAuth, RoleHome } from "./ui/Layout";

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: "/change-password", element: <ChangePasswordPage /> },
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <RoleHome /> },
          { path: "/practice", element: <ProblemListPage /> },
          { path: "/practice/problems/:problemId", element: <ProblemPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);

export function App() {
  return <RouterProvider router={router} />;
}
