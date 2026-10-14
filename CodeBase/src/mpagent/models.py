"""Data models: the exact shape of every file the pipeline writes.

Pydantic checks types when an object is created and can save/load the object as JSON.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FileKind(str, Enum):
    INSTALLER = "installer"
    DOCUMENT = "document"
    METADATA = "metadata"
    UNSUPPORTED = "unsupported"


class InputFile(BaseModel):
    """One file found in the plug-in's input folder."""

    name: str
    kind: FileKind
    size_bytes: int
    sha256: str


class Document(BaseModel):
    """A document whose text was extracted, e.g. the description or a user guide."""

    doc_id: str = Field(description="Short ID used for citations, e.g. 'D1'")
    source_file: str
    format: str = Field(description="File extension without the dot, e.g. 'txt', 'pdf'")
    text_file: str = Field(description="Path of the extracted text, relative to the run folder")
    line_count: int
    char_count: int
    warnings: list[str] = []


class InstallerInfo(BaseModel):
    """Facts about the installer file. Nothing here comes from running it."""

    file: str
    type: str = Field(description="'msi', 'exe' or 'zip-bundle'")
    size_bytes: int
    sha256: str
    signer_subject: str | None = Field(
        default=None, description="Certificate subject the file claims, e.g. 'CN=Kleen Software GmbH, ...'"
    )
    signer_name: str | None = Field(default=None, description="The CN part of signer_subject")


class InstalledFile(BaseModel):
    """A file the installer would place on disk."""

    name: str
    install_path: str = Field(description="Full target path, starting with a placeholder such as %AppData%")
    size_bytes: int | None = None
    version: str | None = None
    condition: str | None = Field(default=None, description="Installed only when this condition is true")


class CustomActionInfo(BaseModel):
    """Extra logic the installer runs besides copying files."""

    name: str
    type_code: int
    kind: str = Field(description="What the action does, in plain words")
    flags: list[str] = []
    source: str | None = None
    target: str | None = None


class UpgradeRule(BaseModel):
    upgrade_code: str
    version_min: str | None = None
    version_max: str | None = None
    only_detect: bool = Field(description="True: only detects other versions (e.g. to block downgrades), removes nothing")
    removes_older: bool


class RegistryEntry(BaseModel):
    root: str
    key: str
    name: str | None = None
    value: str | None = None


class BundleCommand(BaseModel):
    global_name: str | None = None
    local_name: str | None = None
    group: str | None = None


class RuntimeRequirement(BaseModel):
    scope: str = Field(description="'package', 'components', or the ModuleName of a component entry")
    os: str | None = None
    platform: str | None = None
    series_min: str | None = None
    series_max: str | None = None


class BundleComponent(BaseModel):
    app_name: str | None = None
    module_name: str | None = None
    app_type: str | None = None
    description: str | None = None
    load_on_startup: str | None = None
    load_on_command: str | None = None
    commands: list[BundleCommand] = []


class BundleManifest(BaseModel):
    """Facts from an Autodesk PackageContents.xml (the plug-in's own manifest)."""

    source: str = Field(description="Where the manifest was found inside the installer")
    install_path: str | None = None
    name: str | None = None
    app_version: str | None = None
    author: str | None = None
    description: str | None = None
    product_code: str | None = None
    upgrade_code: str | None = None
    company_name: str | None = None
    company_url: str | None = None
    company_email: str | None = None
    runtime_requirements: list[RuntimeRequirement] = []
    components: list[BundleComponent] = []


class EmbeddedDocument(BaseModel):
    """A readable document shipped inside the installer, e.g. Help.html."""

    doc_id: str = Field(description="Citation ID, e.g. 'I1' (I = from the installer)")
    name: str
    install_path: str | None = None
    text_file: str
    line_count: int
    char_count: int


class InstallerFacts(BaseModel):
    """Output of Stage 1: what the installer contains and would do. Nothing was installed or run."""

    installer_file: str
    installer_type: str
    sha256: str
    properties: dict[str, str] = Field(default_factory=dict, description="Selected MSI properties")
    install_scope: str | None = Field(default=None, description="'per-machine', 'per-user' or 'dual'")
    install_roots: list[str] = Field(default_factory=list, description="Top-level folders files go to")
    files: list[InstalledFile] = []
    custom_actions: list[CustomActionInfo] = []
    upgrade_rules: list[UpgradeRule] = []
    launch_conditions: list[dict[str, str | None]] = []
    registry: list[RegistryEntry] = []
    bundles: list[BundleManifest] = []
    embedded_documents: list[EmbeddedDocument] = []
    notable_files: list[str] = Field(default_factory=list, description="Files worth attention, with the reason")
    warnings: list[str] = []


class IntakeManifest(BaseModel):
    """Output of Stage 0: everything later stages need to know about the inputs."""

    plugin: str
    input_dir: str
    created_at: datetime
    files: list[InputFile]
    documents: list[Document]
    installer: InstallerInfo
    metadata_file: str | None = None
    estimated_tokens: int = Field(description="Rough size of all document text in LLM tokens (chars / 4)")
    warnings: list[str] = []


# ================================================================ test plan (Agent 1 output, ARCHITECTURE.md §6.1)
# These models are sent to OpenAI as strict structured output, so every field is required (no defaults)
# and there are no free-form dicts: key/value data is a list of KeyValue.

Scalar = str | int | float | bool | None


class Category(str, Enum):
    ENV = "ENV"
    INST = "INST"
    LOAD = "LOAD"
    UNIN = "UNIN"


class Origin(str, Enum):
    AGENT = "agent"
    BUILT_IN = "built-in"


class Priority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Check(str, Enum):
    """How the verdict engine compares an observed value with the expected one (ARCHITECTURE.md §5)."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    CONTAINS = "contains"
    MATCHES = "matches"
    # decided by code from the raw Snapshot UI tree, not from Agent 2's value (FUNCTIONAL_TESTS_PLAN.md L4, L11)
    WINDOW_IN_UI = "window_in_ui"  # value: regex of a window/document title inside the host window
    SEEN_IN_UI = "seen_in_ui"  # value: exact element name (e.g. a ribbon tab label) inside the host window

UI_CHECKS = {Check.WINDOW_IN_UI, Check.SEEN_IN_UI}


class Citation(BaseModel):
    """Where a claim comes from. The self-check verifies that `quote` really appears in `doc`."""

    doc: str = Field(
        description="Source ID from the evidence pack: 'D1'.. (documents), 'I1'.. (embedded in the installer) or 'F1' (installer facts)"
    )
    line: int | None = Field(description="Line number where the quote starts, if known")
    quote: str = Field(description="Exact text copied from the source")


class Expectation(BaseModel):
    """One check on one observed key, e.g. install_exit_code in [0, 3010]."""

    key: str = Field(description="snake_case observation key; must be listed in the test's `observe`")
    check: Check
    value: Scalar = Field(description="Expected value for equals/not_equals/contains/matches; null otherwise")
    values: list[str] | None = Field(description="Allowed values for 'in'; null otherwise")


class TestCase(BaseModel):
    __test__ = False  # not a pytest test class

    id: str = Field(description="Unique ID: <CATEGORY>-<3 digits>, e.g. INST-002")
    origin: Origin = Field(description="'agent' for every test Agent 1 writes; 'built-in' is reserved for code")
    category: Category
    title: str
    source: Citation | None = Field(description="Required for agent tests; null only for built-in tests")
    preconditions: list[str] = Field(description="IDs of tests that must PASS first, e.g. ['ENV-000', 'INST-001']")
    steps: list[str] = Field(description="Plain-language intents for Agent 2, e.g. 'Install the MSI silently with a log'")
    observe: list[str] = Field(description="snake_case keys Agent 2 must report, e.g. ['install_exit_code']")
    expected: list[Expectation]
    priority: Priority


class InstallerRef(BaseModel):
    file: str
    type: str = Field(description="'msi', 'exe' or 'zip-bundle'")
    product_code: str | None
    signer_claimed: str | None


class AppInfo(BaseModel):
    name: str
    publisher: str | None
    version: str | None
    host_id: str = Field(description="A host-notes ID from the catalogue, 'none' (standalone app) or 'unknown'")
    host_evidence: list[Citation] = Field(description="Why this host was chosen; empty only for 'unknown'")
    host_versions: list[str] = Field(description="Supported host versions named in the sources, e.g. ['2027']")
    installer: InstallerRef


class EntryPointKind(str, Enum):
    RIBBON_TAB = "ribbon_tab"
    MENU = "menu"
    TOOLBAR = "toolbar"
    COMMAND = "command"
    OWN_WINDOW = "own_window"


# Kinds that are visible in the host's UI right after start, so a LOAD test can look for them
VISIBLE_ENTRY_POINTS = {EntryPointKind.RIBBON_TAB, EntryPointKind.MENU, EntryPointKind.TOOLBAR}


class EntryPoint(BaseModel):
    """Where the app shows up in its host, as its documents describe it (FUNCTIONAL_TESTS_PLAN.md §4.1)."""

    kind: EntryPointKind
    label: str = Field(description="The exact text the UI should show, e.g. the ribbon tab name, copied from a source")
    items: list[str] = Field(description="Buttons or commands inside it, only names quoted in a source")
    use_context: str | None = Field(
        description="What must be open to *use* the app (e.g. a kind of project or drawing), as the docs say; null if not stated")
    sources: list[Citation] = Field(description="Quotes for the label, items and use_context")


class Summary(BaseModel):
    """Rendered into understanding.md."""

    purpose: str
    install_footprint: list[str]
    commands_or_ui: list[str]
    entry_point: EntryPoint | None = Field(description="The app's entry point in the host UI; null if not documented")
    open_questions: list[str]


class TestPlan(BaseModel):
    """Agent 1's output and the content of testcases.yaml (ENV-000 is added by code afterwards)."""

    __test__ = False  # not a pytest test class

    app: AppInfo
    summary: Summary
    required_env: list[str] = Field(description="Every ${PLACEHOLDER} name used in steps or expected")
    testcases: list[TestCase]


# ================================================================ execution (ARCHITECTURE.md §6.2, §6.3)


class KeyValue(BaseModel):
    key: str
    value: Scalar


class Observation(BaseModel):
    """One test's raw result, written by Agent 2's record_observation tool into observations.json. No status."""

    test_id: str
    executed: bool = Field(description="False if Agent 2 could not carry out the steps")
    observed: list[KeyValue] = Field(description="One entry per key in the test's `observe` list")
    evidence: list[str] = Field(description="Paths relative to the run folder, e.g. 'evidence/INST-001_install.log'")
    notes: str | None


class Agent2Result(BaseModel):
    """Agent 2's final output; the observations themselves were already recorded per test."""

    done: bool
    env: list[KeyValue] = Field(description="Resolved value of every required_env placeholder")


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"  # only a human looking at the screenshot can decide
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class CheckResult(BaseModel):
    key: str
    check: Check
    expected: Scalar | list[str]
    observed: Scalar
    ok: bool
    needs_review: bool = False
    reported: Scalar = Field(default=None, description="For UI checks: Agent 2's own value, shown but not used")


class HostLocate(BaseModel):
    """How code finds the host executable: a registry value under a product key whose `match_value` matches."""

    registry_root: str = Field(description=r"e.g. 'HKLM:\SOFTWARE\Vendor\Product'; product keys are searched up to 2 levels below")
    value: str = Field(description="Registry value holding the install folder, e.g. 'InstallLocation'")
    match_value: str = Field(description="Registry value used to pick the product key, e.g. 'ProductName'")
    match: str = Field(description="Regular expression the match_value must match")


class HostProcess(BaseModel):
    """`host_process` front matter of a host-notes file: the host facts code needs (FUNCTIONAL_TESTS_PLAN.md L9)."""

    locate: HostLocate
    executable: str = Field(description="File name inside the install folder, e.g. 'host.exe'")
    args: list[str] = Field(default_factory=list, description="Exact launch arguments")
    processes: list[str] = Field(description="Process image names, e.g. ['host.exe']")
    main_window: str = Field(description="Regular expression for the host's main window title")
    new_document: str = Field(description="Regular expression for the title of a new default document")


class TestResult(BaseModel):
    """Verdict for one test, decided by code (verdict engine), written to results.json."""

    __test__ = False  # not a pytest test class

    test_id: str
    origin: Origin
    status: Status
    checks: list[CheckResult]
    evidence: list[str]
    notes: str | None


class RunResults(BaseModel):
    """results.json: every verdict of one run plus the counts per status."""

    app: str
    run_folder: str
    agent2_finished: bool
    counts: dict[str, int]
    results: list[TestResult]
