import { ReactNode } from "react";
import AppNavbar from "@/components/navigation/AppNavbar";
import styles from "@/styles/analytics-flow.module.css";

interface AppFrameProps {
  children: ReactNode;
}

export default function AppFrame({ children }: AppFrameProps) {
  return (
    <div className={styles.appShell}>
      <AppNavbar />
      <main className={styles.mainContent}>{children}</main>
    </div>
  );
}
