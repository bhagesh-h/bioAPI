# Roadmap

Candidate additions to bioAPI, gathered by comparing the current 44 endpoints
against what comparable tools expose and against what the dependencies already
in the image can do. **Nothing here is implemented.** It is a shortlist to argue
with, not a promise.

The ordering principle: bioAPI already ships Biopython and pysam, and uses a
narrow slice of both. `app/` imports only `SeqIO`, `Seq` and `SeqRecord` from
Biopython, and calls pysam only for the health probe, VCF reading and SAM/BAM
statistics. Most of the value below therefore needs no new dependency, no new
build stage, and no change to the response envelope.

## A. Capability already in the image, not yet exposed

These are the highest value per unit of effort. Each is a thin service function
plus a route.

| # | Proposal | Draft route | Backed by |
|---|---|---|---|
| A1 | **Melting temperature** for a primer or oligo — Wallace rule, GC-based and nearest-neighbour, with salt correction | `POST /api/v1/sequences/melting-temp` | `Bio.SeqUtils.MeltingTemp` (`Tm_Wallace`, `Tm_GC`, `Tm_NN`) |
| A2 | **Protein properties** — molecular weight, isoelectric point, aromaticity, instability index, GRAVY, secondary-structure fraction, charge at a given pH | `POST /api/v1/sequences/protein-stats` | `Bio.SeqUtils.ProtParam.ProteinAnalysis` |
| A3 | **Molecular weight** for DNA, RNA or protein, single- or double-stranded | `POST /api/v1/sequences/molecular-weight` | `Bio.SeqUtils.molecular_weight` |
| A4 | **ORF finding** — scan all six frames, report start/stop, frame, strand and the peptide, with a minimum-length filter | `POST /api/v1/sequences/orfs` | `Seq.translate` per frame; the standard approach used by tools like [SMS2 ORF Finder](https://www.bioinformatics.org/sms2/orf_find.html) |
| A5 | **Six-frame translation** as its own answer, rather than only frame 1 | `POST /api/v1/sequences/six-frame` | `Bio.Seq` |
| A6 | **Restriction analysis** — cut sites for a named enzyme or a supplier set, with fragment lengths | `POST /api/v1/sequences/restriction-sites` | `Bio.Restriction` |
| A7 | **Codon usage table** for a coding sequence or a whole FASTA file, with relative synonymous codon usage | `POST /api/v1/sequences/codon-usage` | `Bio.Data.CodonTable` plus counting |
| A8 | **Pairwise alignment** — global or local, returning score, identity and the aligned strings | `POST /api/v1/sequences/align` | `Bio.Align.PairwiseAligner` |
| A9 | **SAM/BAM operations** beyond statistics — query a region, report depth or coverage, filter by MAPQ or flag | `POST /api/v1/files/bam/*` | pysam, already a dependency and already loaded by the readiness probe |

A1, A2 and A4 are the ones a bench user asks for most often, and none of the
three has any equivalent in the current API.

## B. File-level operations that comparable tools have

Measured against [SeqKit](https://bioinf.shenwei.me/seqkit/), which is the
closest command-line equivalent to the FASTA and FASTQ groups.

| # | Proposal | Draft route | Note |
|---|---|---|---|
| B1 | **Search a file for a motif** and report which records contain it and where | `POST /api/v1/fasta/locate` | `sequences/find-motif` works on one pasted sequence only; the file-level case is the common one. SeqKit's `grep` and `locate` also allow mismatches |
| B2 | **Sort records** by length, name or sequence | `POST /api/v1/fasta/sort` | SeqKit `sort`. No ordering operation exists today |
| B3 | **Sliding windows** — cut every record into overlapping windows of size *n*, step *s* | `POST /api/v1/fasta/sliding` | SeqKit `sliding`. `extract-subsequence` only takes one fixed range |
| B4 | **Translate a whole FASTA file**, not just one sequence | `POST /api/v1/fasta/translate` | Currently you would have to split the file and call `sequences/translate` per record |
| B5 | **Regex replace** on identifiers or sequences | `POST /api/v1/fasta/replace` | `rename-sequences` needs an explicit map, which does not scale to a whole file |
| B6 | **Shuffle** record order, with a seed | `POST /api/v1/fasta/shuffle` | Pairs with the existing `sample-sequences` |
| B7 | **Records common to several files** | `POST /api/v1/fasta/common` | `find-unique` deduplicates within one document; this is the across-documents case |
| B8 | **Paired-end FASTQ** — validate that two files pair up, report orphans, filter as a pair | `POST /api/v1/fastq/pair` | The clearest gap for real sequencing work: reads usually arrive as R1/R2 and every operation today treats a file as standalone |
| B9 | **Quality-encoding conversion** between Sanger, Solexa and Illumina 1.3+ | `POST /api/v1/fastq/convert-encoding` | Requests carry `quality_offset` for reading, but nothing can re-encode a file |
| B10 | **BED region extraction**, alongside the GFF support already there | `POST /api/v1/files/extract-bed` | `extract-gff` covers GFF/GTF; BED is the other format people arrive with |
| B11 | **Amplicon extraction** by primer pair | `POST /api/v1/fasta/amplicon` | SeqKit `amplicon`. Natural companion to A1 |

## C. Shape of the API rather than new biology

| # | Proposal | Why |
|---|---|---|
| C1 | **Asynchronous jobs** — submit, poll status, fetch result, as [EMBL-EBI's Job Dispatcher](https://www.ebi.ac.uk/jdispatcher/) does for its tools | Everything today is synchronous behind a 50 MB cap. Genome-scale files do not fit that model, and a long request is at the mercy of every proxy timeout in between |
| C2 | **Batch requests** — many sequences in one call | The `sequences/*` group takes exactly one sequence, so analysing a thousand means a thousand round trips |
| C3 | **Transparent gzip on every upload** | `fastq/compress-gz` and `decompress-gz` exist, but a `.fasta.gz` sent to `files/stats` is not unpacked. Real files arrive compressed |
| C4 | **Pagination** on per-record output | `fasta/stats` returns a per-sequence breakdown and `files/vcf/extract` a variant list; both grow without bound |
| C5 | **Streaming responses** for conversions | A conversion currently materialises the whole output before the first byte is sent |
| C6 | **Idempotency keys** on POST | A retried upload after a timeout repeats the work; a key would let the server return the first answer instead |

## Suggested first slice

If only one release were possible: **A1, A2, A4 and B9**. They share a single
theme — the primer-and-protein questions that come up at the bench — they need
no new dependency, and B9 closes a hole the existing `quality_offset` field
already implies should be closeable.

## Sources

- [SeqKit](https://bioinf.shenwei.me/seqkit/) and its [command list](https://github.com/shenwei356/seqkit)
- [Bio.SeqUtils.ProtParam](https://biopython.org/docs/latest/api/Bio.SeqUtils.ProtParam.html)
- [Bio.SeqUtils.MeltingTemp](https://biopython.org/docs/latest/api/Bio.SeqUtils.MeltingTemp.html)
- [EMBL-EBI Job Dispatcher](https://www.ebi.ac.uk/jdispatcher/) and the [2024 framework paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11223882/)
- [SMS2 ORF Finder](https://www.bioinformatics.org/sms2/orf_find.html), [Restriction Map](https://www.bioinformatics.org/sms2/rest_map.html) and [Codon Usage](https://www.bioinformatics.org/sms2/codon_usage.html)
