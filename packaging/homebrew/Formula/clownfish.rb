class Clownfish < Formula
  include Language::Python::Virtualenv

  desc "Lightweight, zero-dependency modern terminal emulator"
  homepage "https://github.com/wispsy/clownfish"
  url "https://files.pythonhosted.org/packages/source/c/clownfish/clownfish-0.5.0.tar.gz"
  sha256 "78d0fdb1c9042e79c43ff60fd10db13cf9b3bc04fe0c5f41323b61dd94b8ead0"
  license "MIT"

  depends_on "python@3.14"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "clownfish 0.5.0", shell_output("#{bin}/clownfish --version")
  end
end
