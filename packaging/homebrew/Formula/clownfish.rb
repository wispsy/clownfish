class Clownfish < Formula
  include Language::Python::Virtualenv

  desc "Lightweight, zero-dependency modern terminal emulator"
  homepage "https://github.com/wispsy/clownfish"
  url "https://files.pythonhosted.org/packages/source/c/clownfish/clownfish-0.5.0.tar.gz"
  sha256 "eddb7e0b8a22f23ebe91d38e13c6d1ca1641641d3cecf9e114d1eacc1481bb17"
  license "MIT"

  depends_on "python@3.14"
  depends_on "python-tk@3.14"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "clownfish 0.5.0", shell_output("#{bin}/clownfish --version")
    system Formula["python@3.14"].opt_bin/"python3.14", "-c", "import tkinter; import clownfish"
  end
end
