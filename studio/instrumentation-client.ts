import { initBotId } from "botid/client/core";

// BotID client init (issue #5): attaches classification headers to requests
// hitting the paid entry points, so checkBotId() in those routes can tell
// humans from scripts. Only POSTs are protected — resume/read GETs are cheap.
initBotId({
  protect: [
    { path: "/api/chat", method: "POST" },
    { path: "/api/upload", method: "POST" },
  ],
});
