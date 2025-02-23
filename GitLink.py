import os
import re
import webbrowser
import sublime
import sublime_plugin
import subprocess

HOSTINGS = {
    'github': {
        'url': 'https://github.com/{user}/{repo}/blob/{revision}/{remote_path}{filename}',
        'blame_url': 'https://github.com/{user}/{repo}/blame/{revision}/{remote_path}{filename}',
        'line_param': '#L',
        'line_param_sep': '-L'
    },
    'bitbucket': {
        'url': 'https://bitbucket.org/{user}/{repo}/src/{revision}/{remote_path}{filename}',
        'blame_url': 'https://bitbucket.org/{user}/{repo}/annotate/{revision}/{remote_path}{filename}',
        'line_param': '#cl-',
        'line_param_sep': ':'
    },
    'codebasehq': {
        'url': 'https://{user}.{domain}/projects/{project}/repositories/{repo}/blob/{revision}{remote_path}/{filename}',
        'blame_url': 'https://{user}.{domain}/projects/{project}/repositories/{repo}/blame/{revision}{remote_path}/{filename}',
        'line_param': '#L',
        'line_param_sep': ':'
    },
    'gitlab': {
        'url': 'https://{domain}/{user}/{repo}/-/blob/{revision}/{remote_path}{filename}',
        'blame_url': 'https://{domain}/{user}/{repo}/-/blame/{revision}/{remote_path}{filename}',
        'line_param': '#L',
        'line_param_sep': '-'
    }
}


class GitlinkCommand(sublime_plugin.TextCommand):

    def getoutput(self, command):
        proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True,
        )
        out, err = proc.communicate()
        return_code = proc.returncode
        if return_code != 0:
            raise RuntimeError("Failed to run: '{}' (code:{}) with error: {}".format(
                command, return_code, err.decode().strip())
            )
        return out.decode().strip()

    def run(self, edit, **args):
        # Current file path & filename

        # only works on current open file
        path, filename = os.path.split(self.view.file_name())

        # Switch to cwd of file
        os.chdir(path + "/")

        # Find the remote of the current branch
        local_branch = self.getoutput("git symbolic-ref --short HEAD")
        local_branches = [local_branch, "master", "main"]
        for branch_name in local_branches:
            try:
                remote_name = self.getoutput("git config --get branch.{}.remote".format(branch_name))
                tracking_branch = self.getoutput("git rev-parse --symbolic-full-name {}".format(branch_name))
                remote_branch = self.getoutput("git for-each-ref --format='%(upstream:short)' {}".format(tracking_branch))[len(remote_name)+1:]
                break
            except:
                pass
        if not remote_name:
            return

        remote_url = self.getoutput("git remote get-url {}".format(remote_name))
        remote_url = re.sub('.git$', '', remote_url)

        # Select the right hosting configuration
        for hosting_name, hosting in HOSTINGS.items():
            if hosting_name in remote_url:
                # We found a match, so keep these variable assignments
                break

        # Use ssh, except when the remote url starts with http:// or https://
        use_ssh = re.match(r'^https?://', remote_url) is None
        if use_ssh:
            # Allow `ssh://` and a port to be part of the remote
            project = None
            match = re.match(
                r'^(?:ssh://)?([^:]+):\d*/?([^/]+)/([^/]+)',
                remote_url
            )
            if match:
                pieces = match.groups()
                domain, user, repo = pieces
            else:
                # failsafe if regex doesn't match
                # Below index lookups always succeed, no matter whether the
                # split character exists
                domain = remote_url.split(':', 1)[0].split('@', 1)[-1]
                pieces = remote_url.split(':', 1)[-1].split("/")
                if hosting_name == 'codebasehq':
                    # format is codebasehq.com:{user}/{project}/{repo}.git
                    user, project, repo = pieces
                else:
                    # format is {domain}:{user}/{repo}.git
                    user, repo = pieces

            # `domain` may be an alias configured in ssh
            try:
                ssh_output = self.getoutput("ssh -G " + domain)
            except:  # noqa intended unconditional except
                # This is just an attempt at being smart. Let's not crash if
                # it didn't work
                pass
            if ssh_output:
                match = re.search(r'hostname (.*)', ssh_output, re.MULTILINE)
                if match:
                    domain = match.group(1)

        else:
            # HTTP repository
            if hosting_name == 'codebasehq':
                # format is {user}.codebasehq.com/{project}/{repo}.git
                domain, project, repo = remote_url.split("/")
                # user is first segment of domain
                user, domain = domain.split('.', 1)
            else:
                # format is {domain}/{user}/{repo}.git
                domain, user, repo = remote_url.split("://")[-1].split("/")
                project = None

        # Find top level repo in current dir structure
        remote_path = self.getoutput("git rev-parse --show-prefix")

        # Find the current revision
        revision = self.getoutput("git rev-parse HEAD")
        if revision == self.getoutput("git rev-parse {}".format(tracking_branch)):
            revision = remote_branch

        # Choose the view type we'll use
        if 'blame' in args and args['blame']:
            view_type = 'blame_url'
        else:
            view_type = 'url'

        # Build the URL
        url = hosting[view_type].format(
            domain=domain,
            user=user,
            project=project,
            repo=repo,
            revision=revision,
            remote_path=remote_path,
            filename=filename)

        if args['line']:
            region = self.view.sel()[0]
            first_line = self.view.rowcol(region.begin())[0] + 1
            last_line = self.view.rowcol(region.end())[0] + 1
            if first_line == last_line:
                url += "{0}{1}".format(hosting['line_param'], first_line)
            else:
                url += "{0}{1}{2}{3}".format(hosting['line_param'], first_line, hosting['line_param_sep'], last_line)

        if args['web']:
            webbrowser.open_new_tab(url)
        else:
            sublime.set_clipboard(url)
            sublime.status_message('Git URL has been copied to clipboard')
