class Clownfish < Formula
  include Language::Python::Virtualenv

  desc "Lightweight, zero-dependency modern terminal emulator"
  homepage "https://github.com/wispsy/clownfish"
  url "https://files.pythonhosted.org/packages/source/c/clownfish/clownfish-0.6.3.tar.gz"
  sha256 "6300cfb7c9c1c1e78540bd00caef005ef2328b58a4cea29723556f4aa37999de"
  license "MIT"

  depends_on "python@3.14"
  depends_on "python-tk@3.14"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "clownfish 0.6.3", shell_output("#{bin}/clownfish --version")
    system libexec/"bin/python", "-c", "import tkinter; import clownfish"
  end
end
