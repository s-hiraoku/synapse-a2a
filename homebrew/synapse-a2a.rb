class SynapseA2a < Formula
  desc "Agent-to-Agent communication protocol for CLI agents"
  homepage "https://github.com/s-hiraoku/synapse-a2a"
  url "https://files.pythonhosted.org/packages/3f/c2/3bcf39254e9997bb25c922e037b7e68749a0cc2cdb48c49e67cec09d1e06/synapse_a2a-0.5.0.tar.gz"
  sha256 "a9469fe86857842c95d109ef8823f9f7d18651c5f6e090e532009f1d2263e733"
  license "MIT"

  depends_on "python@3.12"

  # Prevent Homebrew from rewriting @rpath dylib IDs in native extensions.
  # pydantic_core ships Rust-compiled .so files with @rpath install names
  # that lack headerpad space for Homebrew's absolute path rewriting.
  preserve_rpath

  def install
    venv = libexec/"venv"
    system Formula["python@3.12"].opt_bin/"python3.12", "-m", "venv", venv
    system venv/"bin/pip", "install", "--upgrade", "pip"
    system venv/"bin/pip", "install", cached_download

    # Wrapper script delegates to the venv binary
    (bin/"synapse").write <<~SH
      #!/bin/bash
      exec "#{venv}/bin/synapse" "$@"
    SH
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/synapse --version")
  end
end
