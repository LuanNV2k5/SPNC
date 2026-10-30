import { createBrowserRouter, Navigate, Outlet, RouterProvider } from "react-router";
import { ChangePasswordPage } from "./features/auth/ChangePasswordPage";
import { LoginPage } from "./features/auth/LoginPage";
import { MyClassesPage } from "./features/practice/MyClassesPage";
import { ProblemListPage } from "./features/practice/ProblemListPage";
import { ProblemPage } from "./features/practice/ProblemPage";
import { ClassesPage } from "./features/teacher/ClassesPage";
import { ClassPage } from "./features/teacher/ClassPage";
import { LiveProvider } from "./features/teacher/LiveProvider";
import { SessionPage } from "./features/teacher/SessionPage";
import { StudentPage } from "./features/teacher/StudentPage";
import { ProblemEditorPage } from "./features/teacher/ProblemEditorPage";
import { ProblemsPage } from "./features/teacher/ProblemsPage";
import { ExamsPage } from "./features/teacher/ExamsPage";
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
          { path: "/classes", element: <MyClassesPage /> },
          {
            // One teacher WebSocket for all teacher pages of this tab (docs/47 D4)
            path: "/teacher",
            element: (
              <LiveProvider>
                <Outlet />
              </LiveProvider>
            ),
            children: [
              { index: true, element: <Navigate to="/teacher/classes" replace /> },
              { path: "classes", element: <ClassesPage /> },
              { path: "classes/:classId", element: <ClassPage /> },
              { path: "classes/:classId/students/:studentId", element: <StudentPage /> },
              { path: "classes/:classId/students/:studentId/sessions/:sessionId", element: <SessionPage /> },
              { path: "problems", element: <ProblemsPage /> },
              { path: "problems/new", element: <ProblemEditorPage /> },
              { path: "problems/:problemId", element: <ProblemEditorPage /> },
              { path: "exams", element: <ExamsPage /> },
              { path: "exams/:examId", element: <ExamsPage /> },
            ],
          },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);

export function App() {
  return <RouterProvider router={router} />;
}
