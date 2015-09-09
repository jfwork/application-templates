#!/usr/bin/env python
# gen_template_doc.py
# Kyle Liberti <kliberti@redhat.com>, Jonathan Dowland <jdowland@redhat.com>
# ver:  Python 3
# Desc: Generates application-template documentation by cloning application-template 
#       repository, then translating information from template JSON files into 
#       template asciidoctor files, and stores them in the a directory(Specified by
#       TEMPLATE_DOCS variable).
# 
# Notes: NEEDS TO BE CLEANED UP

import json
import os
import sys
import re
from ptemplate.template import Template

GIT_REPO = "https://github.com/jboss-openshift/application-templates.git"
REPO_NAME = "application-templates/"
TEMPLATE_DOCS = "docs/"
APPLICATION_DIRECTORIES = ("amq","eap","webserver")
ignore_dirs = ['docs', '.git']

LINKS =  {"jboss-eap6-openshift:${EAP_RELEASE}":                "../../eap/eap-openshift{outfilesuffix}[`jboss-eap-6/eap-openshift`]", \
          "jboss-webserver3-tomcat7-openshift:${JWS_RELEASE}":  "../../webserver/tomcat7-openshift{outfilesuffix}[`jboss-webserver/tomcat7-openshift`]", \
          "jboss-webserver3-tomcat8-openshift:${JWS_RELEASE}":  "../../webserver/tomcat8-openshift{outfilesuffix}[`jboss-webserver/tomcat8-openshift`]"};

PARAMETER_VALUES = {"APPLICATION_HOSTNAME": "secure-app.test.router.default.local", \
                   "GIT_URI": "https://github.com/jboss-openshift/openshift-examples.git", \
                   "GIT_REF": "master", \
                   "GIT_CONTEXT_DIR": "helloworld", \
                   "GITHUB_TRIGGER_SECRET": "secret101", \
                   "GENERIC_TRIGGER_SECRET": "secret101"}

autogen_warning="""////
    AUTOGENERATED FILE - this file was generated via ./gen_template_docs.py.
    Changes to .adoc or HTML files may be overwritten! Please change the
    generator or the input template (./*.in)
////

"""

def generate_templates():
    for directory in set(os.listdir('.')) - set(ignore_dirs):
        if not os.path.isdir(directory):
            continue

        if not os.path.exists(TEMPLATE_DOCS + directory):
           os.makedirs(TEMPLATE_DOCS + directory)

        for template in os.listdir(directory):
            # skip editor temp files
            if template[-4:] == '.swp':
                continue
            with open(directory + "/" + template) as data_file:
                data = json.load(data_file)

                if not 'labels' in data or not "template" in data["labels"]:
                    sys.stderr.write("no template label for template %s, can't generate documentation\n"%\
                        (directory + "/" + template))
                    continue

                template_doc = TEMPLATE_DOCS + directory + "/" + data["labels"]["template"] + ".adoc"

                with open(template_doc, "w") as text_file:
                    text_file.write(autogen_warning)
                    text_file.write(createTemplate(data, directory, template))

def createTemplate(data, directory, template_file):
    templater = Template()
    templater.template = open('./template.adoc.in').read()

    tdata = { "template": data['labels']['template'], }

    # Fill in the template description, if supplied
    if 'annotations' in data['metadata'] and 'description' in data['metadata']['annotations']:
        tdata['description'] = data['metadata']['annotations']['description']

    # Fill in template parameters table, if there are any
    if ("parameters" in data and "objects" in data) and len(data["parameters"]) > 0:
        tdata['parameters'] = [{ 'parametertable': createParameterTable(data) }]

    if "objects" in data:
        tdata['objects'] = [{}]

        # Fill in sections if they are present in the JSON (createObjectTable version)
        for kind in ['Service', 'Route', 'BuildConfig', 'PersistentVolumeClaim']:
            if 0 >= len([ x for x in data["objects"] if kind == x["kind"] ]):
                continue
            tdata['objects'][0][kind] = [{ "table": createObjectTable(data, kind) }]

        # Fill in sections if they are present in the JSON (createContainerTable version)
        for kind in ['image', 'readinessProbe', 'ports', 'env']:
            if 0 >= len([obj for obj in data["objects"] if obj["kind"] == "DeploymentConfig"]):
                continue
            tdata['objects'][0][kind] = [{ "table": createContainerTable(data, kind) }]

        # Fill in sections if they are present in the JSON (createDeployConfigTable version)
        for kind in ['triggers', 'replicas', 'volumes', 'serviceAccount']:
            if 0 >= len([obj for obj in data["objects"] if obj["kind"] == "DeploymentConfig"]):
                continue
            tdata['objects'][0][kind] = [{ "table": createDeployConfigTable(data, kind) }]

        # the 'secrets' section is not relevant to the secrets templates
        if "secrets" != directory:
            tdata['objects'][0]['secrets'] = [{ "templateabbrev": data['labels']['template'][0:3] }]

        # currently the clustering section applies only to EAP templates
        if "eap" == directory:
            tdata['objects'][0]['clustering'] = [{}]

    return templater.render(tdata)

def possibly_fix_width(text):
    """Heuristic to possibly mark-up text as monospaced if it looks like
       a URL, or an environment variable name, etc."""

    if text in ['', '--']:
        return text

    if text[0] in "$/" or "}" == text[-1] or re.match(r'^[A-Z_\${}:-]+$', text):
        return '`%s`' % text

    return text

def buildRow(columns):
   return "\n|" + " | ".join(map(possibly_fix_width, columns))

def getVolumePurpose(name):
   name = name.split("-")
   if("certificate" in name or "keystore" in name or "secret" in name):
      return "ssl certs"
   elif("amq" in name):
      return "kahadb"
   elif("pvol" in name):
      return name[1]
   else:
      return "--"

# Used for getting image enviorment variables into parameters table and parameter
# descriptions into image environment table 
def getVariableInfo(data, name, value):
   for d in data:
      if(d["name"] == name or name[1:] in d["name"] or d["name"][1:] in name):
         return d[value]
   if(value == "value" and name in PARAMETER_VALUES.keys()):
         return PARAMETER_VALUES[name]
   else:
      return "--"

def createParameterTable(data):
   text = ""
   for param in data["parameters"]:
      deploy = [d["spec"]["template"]["spec"]["containers"][0]["env"] for d in data["objects"] if d["kind"] == "DeploymentConfig"]
      environment = [item for sublist in deploy for item in sublist]
      envVar = getVariableInfo(environment, param["name"], "name")
      value = param["value"] if param.get("value") else getVariableInfo(environment, param["name"], "value")
      req = param["required"] if "required" in param else "?"
      columns = [param["name"], envVar, param["description"], value, req]
      text += buildRow(columns)
   return text

def createObjectTable(data, tableKind):
   text = ""
   columns =[]
   for obj in data["objects"]:
      if obj["kind"] ==  'Service' and tableKind == 'Service':
         columns = [obj["metadata"]["name"], str(obj["spec"]["ports"][0]["port"]), obj["metadata"]["annotations"]["description"] ]
      elif obj["kind"] ==  'Route' and tableKind == 'Route':
         if(obj["spec"].get("tls")):
            columns = [obj["id"], ("TLS "+ obj["spec"]["tls"]["termination"]), obj["spec"]["host"]]
         else:
            columns = [obj["id"], "none", obj["spec"]["host"]]
      elif obj["kind"] ==  'BuildConfig' and tableKind == 'BuildConfig':
         s2i = obj["spec"]["strategy"]["sourceStrategy"]["from"]["name"]
         columns = [s2i," link:" + LINKS[s2i], obj["spec"]["output"]["to"]["name"], ", ".join({x["type"] for x in obj["spec"]["triggers"] }) ]
      elif obj["kind"] ==  'PersistentVolumeClaim' and tableKind == 'PersistentVolumeClaim':
         columns = [obj["metadata"]["name"], obj["spec"]["accessModes"][0]]
      if(obj["kind"] == tableKind):
         text += buildRow(columns)
   return text

def createDeployConfigTable(data, table):
   text = ""
   deploymentConfig = (obj for obj in data["objects"] if obj["kind"] == "DeploymentConfig")
   for obj in deploymentConfig: 
      columns = []
      deployment = obj["metadata"]["name"]
      spec = obj["spec"]
      template = spec["template"]["spec"]
      if(template.get(table) or spec.get(table)):
          if table == "triggers":
             columns = [deployment, spec["triggers"][0]["type"] ]
          elif table == "replicas":
             columns = [deployment, str(spec["replicas"]) ]
          elif table == "serviceAccount":
                columns = [deployment, template["serviceAccount"]]
          elif table == "volumes":
                volumeMount = obj["spec"]["template"]["spec"]["containers"][0]["volumeMounts"][0]
                name = template["volumes"][0]["name"]
                readOnly = str(volumeMount["readOnly"]) if "readOnly" in volumeMount else "false"
                columns = [deployment, name, volumeMount["mountPath"], getVolumePurpose(name), readOnly]
          text += buildRow(columns)
   return text

def createContainerTable(data, table):
   text = ""
   deploymentConfig = (obj for obj in data["objects"] if obj["kind"] == "DeploymentConfig")
   for obj in deploymentConfig:
      columns = []
      deployment = obj["metadata"]["name"]
      container = obj["spec"]["template"]["spec"]["containers"][0]
      if table == "image":
         columns = [deployment, container["image"]]
         text += buildRow(columns)
      elif table == "readinessProbe": #abstract out
         if container.get("readinessProbe"):
            text += ("\n." + deployment + "\n----\n" \
            + " ".join(container["readinessProbe"]["exec"]["command"]) \
            + "\n----\n")
      elif table == "ports":
         text += "\n." + str(len(container["ports"])) + "+| `" + deployment + "`"
         ports = container["ports"]
         for p in ports:
            columns = ["name", "containerPort", "protocol"]
            columns = [str(p[col]) if p.get(col) else "--" for col in columns]
            text += buildRow(columns)
      elif table == "env":
         environment = container["env"]
         text += "\n." + str(len(environment)) + "+| `" + deployment + "`"
         for env in environment:
            columns = [env["name"], getVariableInfo(data["parameters"], env["name"], "description")]
            # TODO: handle valueFrom instead of value
            if "value" in env:
                columns.append(env["value"])
            else:
                columns.append("--")
            text += buildRow(columns)
   return text

fullname = {
    "amq":       "JBoss A-MQ",
    "eap":       "JBoss EAP",
    "webserver": "JBoss Web Server"
}

def generate_readme():
    """Generates a README page for the template documentation."""
    with open('docs/README.adoc','w') as fh:
        fh.write(autogen_warning)
        # page header
        fh.write(open('./README.adoc.in').read())

        for directory in set(os.listdir('.')) - set(ignore_dirs):
            if not os.path.isdir(directory):
                continue
            # section header
            fh.write('\n== %s\n\n' % fullname.get(directory, directory))
            # links
            for template in [ os.path.splitext(x)[0] for x in  os.listdir(directory) ]:
                fh.write("* link:./%s/%s.adoc[%s]\n" % (directory, template, template))

if __name__ == "__main__":
    # expects to be run from the root of the repository
    generate_templates()
    generate_readme()
