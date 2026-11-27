class Clownfish < Formula
  include Language::Python::Virtualenv

  desc "Lightweight, zero-dependency modern terminal emulator"
  homepage "https://github.com/wispsy/clownfish"
  url "https://files.pythonhosted.org/packages/source/c/clownfish/clownfish-0.7.0.tar.gz"
  sha256 "a5a59f1bde70f7260c3b8827c229b619da4298d10561cee2e0470cfe7dc11371"
  license "MIT"

  depends_on "python@3.14"
  depends_on "python-tk@3.14"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "clownfish 0.7.0", shell_output("#{bin}/clownfish --version")
    system libexec/"bin/python", "-c", "import tkinter; import clownfish"
  end
end
