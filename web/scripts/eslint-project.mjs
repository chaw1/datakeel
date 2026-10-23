const visibleText = /[A-Za-z\u4e00-\u9fff]/u;
const rules = {
  "single-component-export": {
    meta: {
      type: "problem",
      schema: [],
      messages: { multiple: "Export one component per file." },
    },
    create(context) {
      const components = [];
      function inspect(node) {
        const declaration = node.declaration;
        if (
          declaration?.type === "FunctionDeclaration" &&
          /^[A-Z]/u.test(declaration.id?.name ?? "")
        )
          components.push(node);
        if (declaration?.type === "VariableDeclaration") {
          for (const item of declaration.declarations) {
            if (
              item.id.type === "Identifier" &&
              /^[A-Z]/u.test(item.id.name) &&
              ["ArrowFunctionExpression", "FunctionExpression"].includes(
                item.init?.type,
              )
            )
              components.push(node);
          }
        }
      }
      return {
        ExportNamedDeclaration: inspect,
        ExportDefaultDeclaration: inspect,
        "Program:exit"() {
          for (const node of components.slice(1))
            context.report({ node, messageId: "multiple" });
        },
      };
    },
  },
  "localized-ui-text": {
    meta: {
      type: "problem",
      schema: [],
      messages: { literal: "Put interface text in src/i18n/en.ts and zh.ts." },
    },
    create(context) {
      return {
        JSXText(node) {
          if (visibleText.test(node.value))
            context.report({ node, messageId: "literal" });
        },
        JSXAttribute(node) {
          if (
            ["aria-label", "placeholder", "alt", "title"].includes(
              node.name.name,
            ) &&
            node.value?.type === "Literal" &&
            typeof node.value.value === "string" &&
            visibleText.test(node.value.value)
          )
            context.report({ node, messageId: "literal" });
        },
      };
    },
  },
};
export default { rules };
