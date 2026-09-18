import {
  AppBridge,
  PostMessageTransport,
} from "@modelcontextprotocol/ext-apps/app-bridge";
window.mountUnfold = async (html, result, resources = true) => {
  if (window.unfoldBridge) await window.unfoldBridge.close();
  const frame = document.createElement("iframe");
  frame.id = "app";
  frame.sandbox = "allow-scripts allow-downloads";
  frame.style = "width:100%;height:1300px;border:0";
  document.body.replaceChildren(frame);
  const capabilities = { serverTools: {}, updateModelContext: {} };
  if (resources) capabilities.serverResources = {};
  const bridge = new AppBridge(
    null,
    { name: "Independent fixture host", version: "1.0.0" },
    capabilities,
    { hostContext: { theme: "dark", displayMode: "inline" } },
  );
  bridge.oncalltool = (args) => window.hostCall(args);
  bridge.onreadresource = (args) => window.hostRead(args);
  bridge.onupdatemodelcontext = async (args) => {
    window.savedContext = args;
    return {};
  };
  bridge.oninitialized = async () => {
    await bridge.sendToolInput({ arguments: {} });
    await bridge.sendToolResult(result);
  };
  await bridge.connect(
    new PostMessageTransport(frame.contentWindow, frame.contentWindow),
  );
  frame.srcdoc = html;
  window.unfoldBridge = bridge;
};
