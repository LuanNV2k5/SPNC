import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { getAccessToken, refreshAccessToken } from "../../api/auth";
import { TeacherSocket, teacherSocketUrl, type SocketStatus, type TeacherNotification } from "../../api/teacherSocket";
import { keys } from "./teacherApi";

interface Live {
  status: SocketStatus;
  /** Subscribe to notifications of a class (kept until the page is left). */
  watch(classId: string): void;
  /** Last notification, for components that react to one session. */
  last: TeacherNotification | null;
}

const Ctx = createContext<Live>({ status: "closed", watch: () => {}, last: null });

/** One teacher WebSocket per tab (docs/47 D4); notifications only invalidate REST queries. */
export function LiveProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<SocketStatus>("connecting");
  const [last, setLast] = useState<TeacherNotification | null>(null);
  const socket = useRef<TeacherSocket | null>(null);
  // Children's effects run before this provider's: remember classes watched before the socket exists
  const watched = useRef(new Set<string>());

  useEffect(() => {
    const s = new TeacherSocket({
      url: teacherSocketUrl(),
      getToken: getAccessToken,
      refresh: refreshAccessToken,
      onStatus: setStatus,
      onResync: () => void qc.invalidateQueries({ queryKey: keys.all }),
      onNotification: (n) => {
        setLast(n);
        // Attention lists of every class, then the student's and the session's data
        void qc.invalidateQueries({ queryKey: ["t", "attention"] });
        if (n.student_id) {
          void qc.invalidateQueries({ queryKey: ["t", "sessions"], predicate: (q) => q.queryKey[3] === n.student_id });
          void qc.invalidateQueries({ queryKey: ["t", "signals"], predicate: (q) => q.queryKey[3] === n.student_id });
        }
        if (n.session_id) void qc.invalidateQueries({ queryKey: keys.timeline(n.session_id) });
      },
    });
    socket.current = s;
    watched.current.forEach((id) => s.subscribe(id));
    return () => {
      s.close();
      socket.current = null;
    };
  }, [qc]);

  const value: Live = { status, last, watch: (classId) => {
      watched.current.add(classId);
      socket.current?.subscribe(classId);
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useLive = () => useContext(Ctx);
