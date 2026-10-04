import { chatStyles } from "@weather/a2ui-client/src/chat";
import "./app";
import "./styles.css";

const style = document.createElement("style");
style.textContent = chatStyles;
document.head.append(style);
window.compare = document.querySelector("compare-app") ?? undefined;
