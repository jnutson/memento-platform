import type { ReactNode } from "react";
import styles from "./Shell.module.css";

export default function Shell({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <span>Memento Loop</span>
        <span className={styles.divider}>/</span>
        <span className={styles.context}>Walmart · Miro Spark</span>
      </header>
      <nav className={styles.sidebar} aria-label="Product navigation">
        <span className={`${styles.item} ${styles.active}`} aria-current="page">Memento Signal</span>
      </nav>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
