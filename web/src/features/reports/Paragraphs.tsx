export function Paragraphs({ body }: { body: string }) {
  return (
    <>
      {body
        .split("\n")
        .filter((line) => line.trim())
        .map((line, index) => {
          if (/^#{1,6} /.test(line))
            return <h4 key={index}>{line.replace(/^#{1,6} /, "")}</h4>;
          if (/^[-*] /.test(line))
            return (
              <p className="report-bullet" key={index}>
                {line.replace(/^[-*] /, "")}
              </p>
            );
          return <p key={index}>{line}</p>;
        })}
    </>
  );
}
