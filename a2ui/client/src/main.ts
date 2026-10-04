import { chatStyles } from "./index";

const style = document.createElement("style");
style.textContent = chatStyles;
document.head.append(style);

const chat = document.querySelector("weather-a2ui-chat")!;
const url = new URLSearchParams(location.search).get("agent");
if (url) chat.setAttribute("agent-url", url);
