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
