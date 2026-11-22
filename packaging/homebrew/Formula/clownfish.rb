class Clownfish < Formula
  include Language::Python::Virtualenv

  desc "Lightweight, zero-dependency modern terminal emulator"
  homepage "https://github.com/wispsy/clownfish"
  url "https://files.pythonhosted.org/packages/source/c/clownfish/clownfish-0.6.3.tar.gz"
  sha256 "5c605aca0182afb772877bd1851177ddb5ee4e627ffdbc9b92561833eaf235d9"
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
