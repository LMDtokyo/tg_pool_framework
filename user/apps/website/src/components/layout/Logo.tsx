import { ScrollLink } from "../ui/ScrollLink";
import logoSrc from "../../assets/logo.png";
import styles from "./Logo.module.css";

export function Logo() {
  return (
    <ScrollLink href="#top" className={styles.logo}>
      <img src={logoSrc} alt="Telegram Andromeda" className={styles.mark} />
    </ScrollLink>
  );
}
