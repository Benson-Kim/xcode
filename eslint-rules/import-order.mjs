const groupFor = (source) => {
  if (source.startsWith(".")) return 2;
  if (source.startsWith("@xcode/")) return 1;
  return 0;
};

export default {
  meta: {
    type: "layout",
    docs: {
      description: "Sort imports into installed, shared, and relative groups",
    },
    fixable: "code",
    schema: [],
    messages: {
      order: "Sort imports into installed, shared, and relative groups.",
    },
  },
  create(context) {
    const sourceCode = context.sourceCode;

    return {
      "Program:exit"(program) {
        const imports = program.body.filter(
          (statement) => statement.type === "ImportDeclaration",
        );
        if (imports.length < 2) return;

        const first = imports[0];
        const last = imports[imports.length - 1];
        const importBlock = program.body.filter(
          (statement) =>
            statement.range[0] >= first.range[0] &&
            statement.range[1] <= last.range[1],
        );
        if (importBlock.length !== imports.length) return;

        for (let i = 1; i < imports.length; i++) {
          const gap = sourceCode.text.slice(
            imports[i - 1].range[1],
            imports[i].range[0],
          );
          if (/\/\/|\/\*/.test(gap)) return;
        }

        const ordered = imports
          .map((node, index) => ({
            node,
            index,
            source: node.source.value,
          }))
          .sort(
            (a, b) =>
              groupFor(a.source) - groupFor(b.source) ||
              a.source.localeCompare(b.source) ||
              a.index - b.index,
          );

        const newline = sourceCode.text.includes("\r\n") ? "\r\n" : "\n";
        let replacement = "";
        let previousGroup = -1;

        for (const item of ordered) {
          const group = groupFor(item.source);
          if (replacement) replacement += group === previousGroup ? newline : newline + newline;
          replacement += sourceCode.getText(item.node);
          previousGroup = group;
        }

        const original = sourceCode.text.slice(first.range[0], last.range[1]);
        if (replacement === original) return;

        context.report({
          node: first,
          messageId: "order",
          fix: (fixer) => fixer.replaceTextRange([first.range[0], last.range[1]], replacement),
        });
      },
    };
  },
};
