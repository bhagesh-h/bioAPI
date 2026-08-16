"""In-memory FASTA and FASTQ parsers.

The string-utility endpoints work on documents supplied inline as JSON, so they
never touch the filesystem. These parsers are deliberately strict: a caller who
sends a malformed document gets a precise message naming the offending record
rather than a silently truncated result.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import FastaParseError, FastqParseError


@dataclass(frozen=True, slots=True)
class FastaRecord:
    """One FASTA entry, split into its identifier, description and sequence."""

    identifier: str
    description: str
    sequence: str

    @property
    def header(self) -> str:
        """The full header line, without the leading ``>``."""
        return f"{self.identifier} {self.description}".rstrip()

    def to_fasta(self, line_width: int | None = 60) -> str:
        """Serialise back to FASTA, wrapping the sequence at ``line_width``."""
        if line_width and line_width > 0 and len(self.sequence) > line_width:
            body = "\n".join(
                self.sequence[i : i + line_width] for i in range(0, len(self.sequence), line_width)
            )
        else:
            body = self.sequence
        return f">{self.header}\n{body}"


@dataclass(frozen=True, slots=True)
class FastqRecord:
    """One FASTQ read: header, sequence, separator comment and quality string."""

    identifier: str
    description: str
    sequence: str
    quality: str
    plus_comment: str = ""

    @property
    def header(self) -> str:
        return f"{self.identifier} {self.description}".rstrip()

    def phred_scores(self, offset: int = 33) -> list[int]:
        """Decode the quality string to Phred scores."""
        return [ord(char) - offset for char in self.quality]

    def mean_quality(self, offset: int = 33) -> float:
        """Mean Phred score, or ``0.0`` for a zero-length read."""
        if not self.quality:
            return 0.0
        return sum(ord(char) - offset for char in self.quality) / len(self.quality)

    def to_fastq(self) -> str:
        return f"@{self.header}\n{self.sequence}\n+{self.plus_comment}\n{self.quality}"


def _split_header(header_body: str) -> tuple[str, str]:
    """Split a header body into ``(identifier, description)``."""
    stripped = header_body.strip()
    if not stripped:
        return "", ""
    identifier, _, description = stripped.partition(" ")
    return identifier, description.strip()


def parse_fasta(document: str) -> list[FastaRecord]:
    """Parse a FASTA document into records.

    Multi-line sequences are joined. Blank lines between records are tolerated,
    because many tools emit them.
    """
    lines = document.strip().splitlines()
    if not lines:
        raise FastaParseError("The FASTA document is empty.")

    records: list[FastaRecord] = []
    header: str | None = None
    chunks: list[str] = []

    def flush() -> None:
        if header is None:
            return
        identifier, description = _split_header(header)
        records.append(FastaRecord(identifier, description, "".join(chunks)))

    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if len(line) == 1 or not line[1:].strip():
                raise FastaParseError(
                    f"Line {number}: header has no identifier.",
                    details={"line": number},
                )
            flush()
            header = line[1:]
            chunks = []
        else:
            if header is None:
                raise FastaParseError(
                    f"Line {number}: sequence data appears before any '>' header.",
                    details={"line": number},
                )
            chunks.append(line)

    flush()

    if not records:
        raise FastaParseError("No FASTA records were found in the document.")
    return records


def render_fasta(records: list[FastaRecord], line_width: int | None = 60) -> str:
    """Serialise records to a FASTA document."""
    return "\n".join(record.to_fasta(line_width) for record in records)


def parse_fastq(document: str) -> list[FastqRecord]:
    """Parse a four-lines-per-read FASTQ document.

    Line-wrapped FASTQ exists but is vanishingly rare and cannot be parsed
    unambiguously, so it is rejected with an explicit message rather than being
    guessed at.
    """
    lines = [line.rstrip("\r") for line in document.strip().splitlines()]

    if not lines:
        raise FastqParseError("The FASTQ document is empty.")

    # Trailing blank lines are common; drop them before the divisibility check.
    while lines and lines[-1].strip() == "":
        lines.pop()

    if len(lines) % 4 != 0:
        raise FastqParseError(
            f"A FASTQ document must have a multiple of four lines; got {len(lines)}. "
            "Line-wrapped FASTQ is not supported.",
            details={"line_count": len(lines)},
        )

    records: list[FastqRecord] = []
    for index in range(0, len(lines), 4):
        read_number = index // 4 + 1
        header, sequence, plus, quality = lines[index : index + 4]

        if not header.startswith("@"):
            raise FastqParseError(
                f"Read {read_number}: the header line must start with '@'.",
                details={"read": read_number},
            )
        if not plus.startswith("+"):
            raise FastqParseError(
                f"Read {read_number}: the third line must start with '+'.",
                details={"read": read_number},
            )
        if len(sequence) != len(quality):
            raise FastqParseError(
                f"Read {read_number}: sequence is {len(sequence)} characters but the "
                f"quality string is {len(quality)}.",
                details={"read": read_number},
            )
        if not sequence:
            raise FastqParseError(
                f"Read {read_number}: the sequence is empty.",
                details={"read": read_number},
            )

        identifier, description = _split_header(header[1:])
        records.append(
            FastqRecord(
                identifier=identifier,
                description=description,
                sequence=sequence,
                quality=quality,
                plus_comment=plus[1:],
            )
        )

    return records


def render_fastq(records: list[FastqRecord]) -> str:
    """Serialise reads to a FASTQ document."""
    return "\n".join(record.to_fastq() for record in records)
